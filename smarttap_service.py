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

from core.contracts import build_clarification_result, build_error_result, build_preview, build_success_result
from core.data_fetcher import fetch_data, supported_agrimet_locations
from core.location_crop_query import LocationCropQuery
from core.variable_registry import variable_label
from core.validation import validate_and_fix_spec, validate_payload
from core.visualizer import create_crop_bar_chart, payload_to_df, png_bytes, vega_spec
from llm.interpretation import get_task_specification


class SmartTapError(Exception):
    pass


CLARIFICATION_LABELS = {
    "location": "the location you want to analyze",
    "time_range": "the time range to plot",
    "variable": "the variable or measurement you want",
    "station": "which AgriMet station or supported city to use",
}


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


def _task_label(task: str) -> str:
    labels = {
        "visualize_timeseries": "time-series chart",
        "statistical_summary": "statistical summary",
        "summarize_crops": "crop summary",
    }
    return labels.get(task, task)


def _partial_spec_summary(spec: Dict[str, Any]) -> str:
    parts: list[str] = []
    if spec.get("task"):
        parts.append(f"task={_task_label(str(spec['task']))}")
    if spec.get("dataset"):
        parts.append(f"dataset={spec['dataset']}")
    if spec.get("variables"):
        labels = [variable_label(value) for value in spec["variables"]]
        parts.append(f"variables={', '.join(labels)}")
    if spec.get("location"):
        parts.append(f"location={spec['location']}")
    if spec.get("crop_filter"):
        parts.append(f"crop={spec['crop_filter']}")
    if spec.get("start_date") and spec.get("end_date"):
        parts.append(f"date_range={spec['start_date']} to {spec['end_date']}")
    return "; ".join(parts)


def _clarification_prompt(spec: Dict[str, Any]) -> str:
    fields = spec.get("clarification_needed") or []
    if not fields:
        return "Please add a little more detail so I can finish the request."

    prompts = [CLARIFICATION_LABELS.get(field, field.replace("_", " ")) for field in fields]
    if len(prompts) == 1:
        missing_text = prompts[0]
    elif len(prompts) == 2:
        missing_text = f"{prompts[0]} and {prompts[1]}"
    else:
        missing_text = ", ".join(prompts[:-1]) + f", and {prompts[-1]}"

    examples: list[str] = []
    if "location" in fields:
        examples.append("a city or county, like Corvallis or Benton County")
    if "time_range" in fields:
        examples.append("a year or date range, like 2024 or January to June 2024")
    if "variable" in fields:
        examples.append("a measurement, like temperature, ETa, precipitation, or applied water")

    prompt = f"I need {missing_text} before I can run this request."

    context = _partial_spec_summary(spec)
    if context:
        prompt += f" So far I have: {context}."

    if spec.get("dataset") == "agrimet":
        if "location" in fields:
            supported = ", ".join(supported_agrimet_locations())
            examples.append(f"one of the currently supported local AgriMet cities: {supported}")
        if "station" in fields:
            supported = ", ".join(supported_agrimet_locations())
            prompt += (
                f" The current local AgriMet dataset only supports these cities/stations: {supported}."
            )
            examples.append(f"a supported station/city such as {supported_agrimet_locations()[0]}")

    if spec.get("dataset") == "openet" and "location" in fields:
        examples.append("an Oregon city or county, like Corvallis or Benton County")

    if spec.get("task") == "summarize_crops" and "location" in fields:
        examples.append("a city or county, like Corvallis or Benton County")

    if examples:
        prompt += " You can reply with " + "; ".join(dict.fromkeys(examples)) + "."
    return prompt


def _clean_followup_location(text: str) -> str:
    cleaned = re.sub(r"\b(in|for|near|around|at|during|from|to)\b", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(19|20)\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z\s]", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def _followup_mentions_time_range(text: str) -> bool:
    lowered = (text or "").lower()
    if re.search(r"\b(19\d{2}|20\d{2})\b", lowered):
        return True
    time_tokens = [
        "last year",
        "this year",
        "yesterday",
        "today",
        "this month",
        "last month",
        "from",
        "between",
        "through",
        "during",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
    return any(token in lowered for token in time_tokens)


def _extract_followup_patch(followup_query: str, pending_spec: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    clarification_fields = list(pending_spec.get("clarification_needed") or [])

    raw_patch: Dict[str, Any] = {}
    try:
        raw_patch = get_task_specification(followup_query)
    except Exception:
        raw_patch = {}

    normalized_patch = validate_and_fix_spec(raw_patch, followup_query)

    if "variable" in clarification_fields and normalized_patch.get("variables"):
        patch["variables"] = normalized_patch["variables"]
        if normalized_patch.get("dataset"):
            patch["dataset"] = normalized_patch["dataset"]
        if normalized_patch.get("interval"):
            patch["interval"] = normalized_patch["interval"]

    if "time_range" in clarification_fields and _followup_mentions_time_range(followup_query):
        if normalized_patch.get("start_date") and normalized_patch.get("end_date"):
            patch["start_date"] = normalized_patch["start_date"]
            patch["end_date"] = normalized_patch["end_date"]
        elif normalized_patch.get("year"):
            year = int(normalized_patch["year"])
            patch["start_date"] = f"{year}-01-01"
            patch["end_date"] = f"{year}-12-31"

    if "location" in clarification_fields or "station" in clarification_fields:
        if raw_patch.get("location"):
            patch["location"] = str(raw_patch["location"]).strip()
        elif normalized_patch.get("location"):
            patch["location"] = str(normalized_patch["location"]).strip()
        else:
            candidate = _clean_followup_location(followup_query)
            if candidate:
                patch["location"] = candidate

        if raw_patch.get("location_type"):
            patch["location_type"] = str(raw_patch["location_type"]).lower().strip()
        elif normalized_patch.get("location_type") and patch.get("location"):
            patch["location_type"] = str(normalized_patch["location_type"]).lower().strip()

        if raw_patch.get("station_id"):
            patch["station_id"] = str(raw_patch["station_id"]).strip()
        elif normalized_patch.get("station_id"):
            patch["station_id"] = str(normalized_patch["station_id"]).strip()

    return patch


def process_clarification_reply(
    followup_query: str,
    pending_spec: Dict[str, Any],
    original_query: str,
) -> Dict[str, Any]:
    merged_spec = dict(pending_spec)
    merged_spec.pop("clarification_needed", None)
    patch = _extract_followup_patch(followup_query, pending_spec)
    confirmed_fields = set(merged_spec.get("confirmed_fields") or [])
    if patch.get("location") or patch.get("station_id"):
        confirmed_fields.add("location")
    if patch.get("start_date") and patch.get("end_date"):
        confirmed_fields.add("time_range")
    if patch.get("variables"):
        confirmed_fields.add("variable")
    if confirmed_fields:
        merged_spec["confirmed_fields"] = sorted(confirmed_fields)
    merged_spec.update({key: value for key, value in patch.items() if value not in (None, "", [], {})})
    combined_query = f"{original_query}\n{followup_query}"
    return process_query(combined_query, spec=merged_spec)


def _run_visualization_task(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
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
        "row_count": len(df),
        "date_range": f"{final_spec.get('start_date')} to {final_spec.get('end_date')}",
    }
    return build_success_result(
        spec=final_spec,
        summary=summary,
        data_preview=preview,
        chart_bytes=png,
        vega_spec=vega,
        files={key: str(value) for key, value in paths.items()},
        validation_report=report,
    )


def _run_statistical_summary(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
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
        "mean": round(float(series.mean()), 3),
        "median": round(float(series.median()), 3),
        "min": round(float(series.min()), 3),
        "max": round(float(series.max()), 3),
        "sum": round(float(series.sum()), 3),
        "count": int(series.count()),
    }
    vega = _build_stat_chart(variable, stats)
    png = _build_stat_png(variable, stats)
    _save_bytes(paths["png"], png)
    _save_json(paths["vega"], vega)

    preview = df.reset_index().head(20)
    summary = {
        "task": final_spec["task"],
        "dataset": final_spec["dataset"],
        "location": final_spec.get("location"),
        "variable": variable,
        **stats,
    }
    return build_success_result(
        spec=final_spec,
        summary=summary,
        data_preview=preview,
        chart_bytes=png,
        vega_spec=vega,
        files={key: str(value) for key, value in paths.items()},
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
    return build_success_result(
        spec=spec,
        summary=summary,
        data_preview=crop_summary.head(20).reset_index(drop=True),
        chart_bytes=png,
        vega_spec=vega,
        files={key: str(value) for key, value in paths.items()},
    )


def process_query(query: str, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        raw_spec = spec if spec is not None else get_task_specification(query)
        fixed_spec = validate_and_fix_spec(raw_spec, query)

        if fixed_spec.get("task") == "error":
            return build_error_result(fixed_spec.get("error_message", "Invalid query."))
        if fixed_spec.get("clarification_needed"):
            return build_clarification_result(
                spec=fixed_spec,
                prompt=_clarification_prompt(fixed_spec),
                fields=list(fixed_spec.get("clarification_needed") or []),
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
