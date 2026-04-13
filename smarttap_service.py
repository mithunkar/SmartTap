from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

cache_dir = Path(__file__).resolve().parent / ".cache" / "matplotlib"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir.parent))

import matplotlib.pyplot as plt
import pandas as pd

from core.contracts import (
    build_clarification_result,
    build_error_result,
    build_preview,
    build_success_result,
)
from core.data_fetcher import fetch_data, supported_agrimet_locations
from core.location_crop_query import LocationCropQuery
from core.validation import validate_and_fix_spec, validate_payload
from core.explanation import build_result_explanation
from core.variable_registry import variable_label
from core.visualizer import create_crop_bar_chart, payload_to_df, png_bytes, vega_spec
from llm.interpretation import get_task_specification


class SmartTapError(Exception):
    pass


def _output_paths(base_name: str) -> Dict[str, Path]:
    output_root = Path("outputs")
    chart_dir = output_root / "charts"
    validation_dir = output_root / "validation"
    chart_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    return {
        "png": chart_dir / f"{base_name}.png",
        "vega": chart_dir / f"{base_name}_vega.json",
        "validation": validation_dir / f"{base_name}_validation.json",
    }


def _base_name() -> str:
    return f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _save_bytes(path: Path, payload: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(payload)


def _init_location_query() -> LocationCropQuery:
    full_gpkg = Path(__file__).parent / "data" / "preliminary_or_field_geopackage.gpkg"
    if full_gpkg.exists():
        return LocationCropQuery(full_oregon_gpkg=str(full_gpkg))
    return LocationCropQuery()


def _clean_location_name(location: str, location_type: str) -> str:
    if location_type == "county" and location.lower().endswith(" county"):
        return location[:-7].strip()
    return location


def _build_stat_chart(variable: str, stats: Dict[str, float]) -> Dict[str, Any]:
    values = [
        {"stat": "Mean", "value": stats["mean"]},
        {"stat": "Median", "value": stats["median"]},
        {"stat": "Min", "value": stats["min"]},
        {"stat": "Max", "value": stats["max"]},
    ]
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": f"{variable} statistical summary",
        "data": {"values": values},
        "mark": "bar",
        "encoding": {
            "x": {"field": "stat", "type": "nominal", "title": "Statistic"},
            "y": {"field": "value", "type": "quantitative", "title": variable},
            "tooltip": [
                {"field": "stat", "type": "nominal"},
                {"field": "value", "type": "quantitative"},
            ],
        },
    }


def _build_stat_png(variable: str, stats: Dict[str, float]) -> bytes:
    labels = ["Mean", "Median", "Min", "Max"]
    values = [stats["mean"], stats["median"], stats["min"], stats["max"]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, values, color="#b85c38")
    ax.set_title(f"{variable} statistical summary")
    ax.set_ylabel(variable)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    output = Path("outputs")
    output.mkdir(exist_ok=True)
    from io import BytesIO

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160)
    plt.close(fig)
    return buffer.getvalue()


def _files_as_strings(paths: Dict[str, Path]) -> Dict[str, str]:
    return {key: str(value) for key, value in paths.items()}


def _resolved_request_text(spec: Dict[str, Any]) -> str:
    parts = []
    variables = spec.get("variables") or []
    if variables:
        labels = ", ".join(variable_label(variable) for variable in variables)
        parts.append(f"variables={labels}")
    if spec.get("location"):
        parts.append(f"location={spec['location']}")
    if spec.get("start_date") and spec.get("end_date"):
        parts.append(f"date_range={spec['start_date']} to {spec['end_date']}")
    if spec.get("year"):
        parts.append(f"year={spec['year']}")
    return ", ".join(parts)


def _build_clarification_prompt(spec: Dict[str, Any], fields: list[str]) -> str:
    details = _resolved_request_text(spec)
    field_names = ", ".join(fields)
    prefix = "I need a bit more detail before I can build the result."
    if details:
        prefix += f" Current request: {details}."

    field_messages = []
    if "variable" in fields:
        field_messages.append("the variable you want to inspect")
    if "location" in fields:
        field_messages.append("the location")
    if "time_range" in fields:
        field_messages.append("the time range")
    if "station" in fields:
        supported = ", ".join(supported_agrimet_locations())
        field_messages.append(
            f"a supported AgriMet location or station choice; the local AgriMet dataset only supports: {supported}"
        )

    if field_messages:
        prefix += f" Please provide {', '.join(field_messages)}."
    else:
        prefix += f" Missing fields: {field_names}."

    return prefix


def _extract_location_from_followup(text: str) -> str | None:
    lowered = " ".join((text or "").strip().lower().replace("_", " ").split())
    if not lowered:
        return None

    for location in supported_agrimet_locations():
        if location in lowered:
            return location.title()

    if " county" in lowered:
        county_name = lowered.split(" county")[0].strip()
        if county_name:
            return f"{county_name.title()} County"

    if lowered.replace(" ", "").isalpha():
        return lowered.title()
    return None


def _extract_date_patch(text: str) -> Dict[str, str]:
    years = sorted({int(value) for value in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")})
    if not years:
        return {}
    if len(years) == 1:
        year = years[0]
        return {"start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}
    return {"start_date": f"{years[0]}-01-01", "end_date": f"{years[-1]}-12-31"}


def _merge_followup_into_pending(followup_query: str, pending_spec: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(pending_spec)
    clarified = set(merged.get("confirmed_fields") or [])
    missing = list(merged.get("clarification_needed") or [])

    location = _extract_location_from_followup(followup_query)
    if location and any(field in missing for field in ["location", "station"]):
        merged["location"] = location
        clarified.add("location")
        missing = [field for field in missing if field not in {"location", "station"}]

    date_patch = _extract_date_patch(followup_query)
    if date_patch and "time_range" in missing:
        merged.update(date_patch)
        clarified.add("time_range")
        missing = [field for field in missing if field != "time_range"]

    merged["confirmed_fields"] = sorted(clarified)
    if missing:
        merged["clarification_needed"] = missing
    else:
        merged.pop("clarification_needed", None)
    return merged


def _run_visualization_task(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    del query
    payload = fetch_data(spec)
    report = validate_payload(payload)
    _save_json(paths["validation"], report)
    if not report["ok"]:
        raise SmartTapError("; ".join(report["errors"]))

    png = png_bytes(payload)
    vega = vega_spec(payload)
    _save_bytes(paths["png"], png)
    _save_json(paths["vega"], vega)

    final_spec, df, variables = payload_to_df(payload)
    preview = build_preview(df)

    summary = {
        "task": final_spec["task"],
        "dataset": final_spec["dataset"],
        "location": final_spec.get("location"),
        "variables": ", ".join(variables),
        "variables_list": variables,
        "row_count": len(df),
        "date_range": f"{final_spec.get('start_date')} to {final_spec.get('end_date')}",
    }

    explanation = build_result_explanation(
        spec=final_spec,
        df=df,
        summary=summary,
        vega_spec=vega,
    )

    return build_success_result(
        spec=final_spec,
        summary=summary,
        explanation=explanation,
        data_preview=preview,
        chart_bytes=png,
        vega_spec=vega,
        files=_files_as_strings(paths),
        validation_report=report,
    )


def _run_statistical_summary(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    del query
    stat_spec = dict(spec)
    if stat_spec.get("dataset") == "openet":
        stat_spec["openet_geo"] = stat_spec.get("openet_geo") or "location"
        stat_spec["aggregation"] = stat_spec.get("aggregation") or "mean"

    payload = fetch_data(stat_spec)
    report = validate_payload(payload)
    _save_json(paths["validation"], report)
    if not report["ok"]:
        raise SmartTapError("; ".join(report["errors"]))

    final_spec, df, variables = payload_to_df(payload)
    if not variables:
        raise SmartTapError("Statistical summary needs at least one numeric variable.")

    variable = variables[0]
    series = df[variable].dropna()
    if series.empty:
        raise SmartTapError(f"No values available for {variable}.")

    stats = {
        "mean":   round(float(series.mean()), 3),
        "median": round(float(series.median()), 3),
        "min":    round(float(series.min()), 3),
        "max":    round(float(series.max()), 3),
        "sum":    round(float(series.sum()), 3),
        "count":  int(series.count()),
    }
    vega = _build_stat_chart(variable, stats)
    png = _build_stat_png(variable, stats)
    _save_bytes(paths["png"], png)
    _save_json(paths["vega"], vega)

    preview = build_preview(df)
    summary = {
        "task": final_spec["task"],
        "dataset": final_spec["dataset"],
        "location": final_spec.get("location"),
        "variable": variable,
        **stats,
    }

    explanation = build_result_explanation(
        spec=final_spec,
        df=df,
        summary=summary,
        vega_spec=vega,
    )

    return build_success_result(
        spec=final_spec,
        summary=summary,
        explanation=explanation,
        data_preview=preview,
        chart_bytes=png,
        vega_spec=vega,
        files=_files_as_strings(paths),
        validation_report=report,
    )


def _run_crop_summary(spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    query_system = _init_location_query()
    location = spec.get("location", "")
    location_type = spec.get("location_type", "city")
    year = int(spec.get("year", 2024))
    clean_location = _clean_location_name(location, location_type)

    if location_type == "city":
        df = query_system.query_crops_by_city(clean_location, year=year)
    elif location_type == "county":
        df = query_system.query_crops_by_county(clean_location, year=year)
    else:
        raise SmartTapError(f"Unsupported location type: {location_type}")

    if df.empty:
        raise SmartTapError(f"No crop data found for {location}.")

    crop_summary = (
        df.groupby(["crop_name", "crop_group"])
        .agg({"OPENET_ID": "count"})
        .reset_index()
        .rename(columns={"crop_name": "Crop", "crop_group": "Group", "OPENET_ID": "Field Count"})
        .sort_values("Field Count", ascending=False)
    )

    png, vega = create_crop_bar_chart(crop_summary, location, year, top_n=15)
    _save_bytes(paths["png"], png)
    _save_json(paths["vega"], vega)

    summary = {
        "task": spec["task"],
        "location": location,
        "location_type": location_type,
        "year": year,
        "total_fields": int(len(df)),
        "total_crops": int(len(crop_summary)),
    }

    explanation = build_result_explanation(
        spec=spec,
        df=crop_summary,
        summary=summary,
        vega_spec=vega,
    )

    return build_success_result(
        spec=spec,
        summary=summary,
        explanation=explanation,
        data_preview=crop_summary.head(20).reset_index(drop=True),
        chart_bytes=png,
        vega_spec=vega,
        files=_files_as_strings(paths),
    )


def process_query(query: str, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        raw_spec = spec if spec is not None else get_task_specification(query)
        fixed_spec = validate_and_fix_spec(raw_spec, query)

        if fixed_spec.get("task") == "error":
            return build_error_result(fixed_spec.get("error_message", "Invalid query."))

        clarification_fields = list(fixed_spec.get("clarification_needed") or [])
        if clarification_fields:
            return build_clarification_result(
                spec=fixed_spec,
                prompt=_build_clarification_prompt(fixed_spec, clarification_fields),
                fields=clarification_fields,
            )

        task = fixed_spec["task"]
        paths = _output_paths(_base_name())

        if task == "visualize_timeseries":
            return _run_visualization_task(query, fixed_spec, paths)
        if task == "statistical_summary":
            return _run_statistical_summary(query, fixed_spec, paths)
        if task == "summarize_crops":
            return _run_crop_summary(fixed_spec, paths)

        return build_error_result(f"Unsupported task: {task}")
    except SmartTapError as exc:
        return build_error_result(str(exc))
    except Exception as exc:
        return build_error_result(str(exc))


def process_clarification_reply(
    *,
    followup_query: str,
    pending_spec: Dict[str, Any],
    original_query: str,
) -> Dict[str, Any]:
    merged = _merge_followup_into_pending(followup_query, pending_spec)
    combined_query = f"{original_query} {followup_query}".strip()
    fixed_spec = validate_and_fix_spec(merged, combined_query)

    clarification_fields = list(fixed_spec.get("clarification_needed") or [])
    if clarification_fields:
        return build_clarification_result(
            spec=fixed_spec,
            prompt=_build_clarification_prompt(fixed_spec, clarification_fields),
            fields=clarification_fields,
        )

    return process_query(original_query, spec=fixed_spec)
