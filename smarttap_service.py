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
from core.variable_registry import AGRIMET_VARIABLES, OPENET_VARIABLES, variable_label
from core.visualizer import create_crop_bar_chart, create_crop_pie_chart, payload_to_df, png_bytes, vega_spec
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


def _paths_with_suffix(paths: Dict[str, Path], suffix: str) -> Dict[str, Path]:
    return {
        key: value.with_name(f"{value.stem}_{suffix}{value.suffix}")
        for key, value in paths.items()
    }


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


def _build_variable_mean_chart(df: pd.DataFrame, variables: list[str], title: str) -> tuple[bytes, Dict[str, Any]]:
    rows = []
    for variable in variables:
        if variable not in df.columns:
            continue
        series = df[variable].dropna()
        if series.empty:
            continue
        rows.append({"variable": variable_label(variable), "value": round(float(series.mean()), 3)})

    vega = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "data": {"values": rows},
        "mark": "bar",
        "encoding": {
            "x": {"field": "variable", "type": "nominal", "title": "Variable"},
            "y": {"field": "value", "type": "quantitative", "title": "Average value"},
            "tooltip": [
                {"field": "variable", "type": "nominal"},
                {"field": "value", "type": "quantitative"},
            ],
        },
    }

    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [row["variable"] for row in rows]
    values = [row["value"] for row in rows]
    ax.bar(labels, values, color="#4c78a8")
    ax.set_title(title)
    ax.set_ylabel("Average value")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    from io import BytesIO

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160)
    plt.close(fig)
    return buffer.getvalue(), vega


def _build_secondary_view(
    *,
    caption: str,
    chart_bytes: bytes,
    vega: Dict[str, Any],
    data_preview: pd.DataFrame | None,
    paths: Dict[str, Path],
) -> Dict[str, Any]:
    _save_bytes(paths["png"], chart_bytes)
    _save_json(paths["vega"], vega)
    return {
        "caption": caption,
        "chart_bytes": chart_bytes,
        "vega_spec": vega,
        "data_preview": data_preview,
        "files": _files_as_strings(paths),
    }


def _files_as_strings(paths: Dict[str, Path]) -> Dict[str, str]:
    return {key: str(value) for key, value in paths.items()}


def _set_optional(summary: Dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        summary[key] = value


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
    secondary_views = []

    summary = {
        "task": final_spec["task"],
        "dataset": final_spec["dataset"],
        "location": final_spec.get("location"),
        "variables": ", ".join(variables),
        "variables_list": variables,
        "row_count": len(df),
        "date_range": f"{final_spec.get('start_date')} to {final_spec.get('end_date')}",
        "evidence_pattern": final_spec.get("evidence_pattern"),
        "chart_package": final_spec.get("chart_package"),
        "source_datasets": ", ".join(final_spec.get("source_datasets") or []),
    }
    _set_optional(summary, "crop_filter", final_spec.get("crop_filter"))

    if final_spec.get("evidence_pattern") == "comparison_multivariate" and len(variables) > 1:
        secondary_paths = _paths_with_suffix(paths, "comparison_summary")
        companion_png, companion_vega = _build_variable_mean_chart(
            df,
            variables,
            "Average values for selected variables",
        )
        secondary_views.append(
            _build_secondary_view(
                caption="This companion chart compares the average value of each selected variable.",
                chart_bytes=companion_png,
                vega=companion_vega,
                data_preview=build_preview(df[variables]),
                paths=secondary_paths,
            )
        )

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
        secondary_views=secondary_views,
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
        "evidence_pattern": final_spec.get("evidence_pattern"),
        "chart_package": final_spec.get("chart_package"),
        **stats,
    }
    _set_optional(summary, "crop_filter", final_spec.get("crop_filter"))

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
        secondary_views=[],
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
    secondary_views = []

    if spec.get("evidence_pattern") in {"ranking_categories", "distribution_categories"}:
        secondary_paths = _paths_with_suffix(paths, "distribution")
        pie_png, pie_vega = create_crop_pie_chart(crop_summary, location, year, top_n=10)
        secondary_views.append(
            _build_secondary_view(
                caption="This companion chart shows the crop-group mix for the same location and year.",
                chart_bytes=pie_png,
                vega=pie_vega,
                data_preview=crop_summary.groupby("Group", as_index=False)["Field Count"].sum(),
                paths=secondary_paths,
            )
        )

    summary = {
        "task": spec["task"],
        "dataset": "openet",
        "location": location,
        "location_type": location_type,
        "year": year,
        "total_fields": int(len(df)),
        "total_crops": int(len(crop_summary)),
        "evidence_pattern": spec.get("evidence_pattern"),
        "chart_package": spec.get("chart_package"),
    }
    _set_optional(summary, "crop_filter", spec.get("crop_filter"))

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
        secondary_views=secondary_views,
    )


def _run_cross_dataset_comparison(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    del query
    source_datasets = list(spec.get("source_datasets") or [])
    variables = list(spec.get("variables") or [])
    dataset_payloads = []
    combined_previews = []

    for index, dataset in enumerate(source_datasets):
        dataset_variables = [
            variable
            for variable in variables
            if (dataset == "openet" and variable in OPENET_VARIABLES)
            or (dataset == "agrimet" and variable in AGRIMET_VARIABLES)
        ]
        if not dataset_variables:
            continue

        dataset_spec = dict(spec)
        dataset_spec["dataset"] = dataset
        dataset_spec["source_datasets"] = [dataset]
        dataset_spec["variables"] = dataset_variables
        dataset_spec["evidence_pattern"] = "trend_single" if len(dataset_variables) == 1 else "comparison_multivariate"

        dataset_paths = paths if index == 0 else _paths_with_suffix(paths, dataset)
        payload = fetch_data(dataset_spec)
        report = validate_payload(payload)
        _save_json(dataset_paths["validation"], report)
        if not report["ok"]:
            raise SmartTapError("; ".join(report["errors"]))

        chart_png = png_bytes(payload)
        chart_vega = vega_spec(payload)
        _save_bytes(dataset_paths["png"], chart_png)
        _save_json(dataset_paths["vega"], chart_vega)

        final_spec, df, final_variables = payload_to_df(payload)
        preview = build_preview(df)
        combined_preview = preview.copy()
        combined_preview["source_dataset"] = dataset
        combined_previews.append(combined_preview)
        dataset_payloads.append((dataset, final_spec, df, final_variables, chart_png, chart_vega, preview, dataset_paths))

    if not dataset_payloads:
        raise SmartTapError("No supported dataset views were available for this evidence package.")

    primary_dataset, primary_spec, primary_df, primary_variables, primary_png, primary_vega, primary_preview, primary_paths = dataset_payloads[0]
    secondary_views = []
    for dataset, final_spec, df, final_variables, chart_png, chart_vega, preview, dataset_paths in dataset_payloads[1:]:
        secondary_views.append(
            _build_secondary_view(
                caption=f"This companion chart shows {', '.join(variable_label(value) for value in final_variables)} from {dataset}.",
                chart_bytes=chart_png,
                vega=chart_vega,
                data_preview=preview,
                paths=dataset_paths,
            )
        )

    summary = {
        "task": spec["task"],
        "dataset": primary_dataset,
        "location": spec.get("location"),
        "variables": ", ".join(variables),
        "variables_list": variables,
        "row_count": sum(len(df) for _, _, df, _, _, _, _, _ in dataset_payloads),
        "date_range": f"{spec.get('start_date')} to {spec.get('end_date')}",
        "evidence_pattern": spec.get("evidence_pattern"),
        "chart_package": spec.get("chart_package"),
        "source_datasets": ", ".join(source_datasets),
        "secondary_view_count": len(secondary_views),
    }
    _set_optional(summary, "crop_filter", spec.get("crop_filter"))

    explanation = build_result_explanation(
        spec=spec,
        df=primary_df,
        summary=summary,
        vega_spec=primary_vega,
    )

    combined_preview = pd.concat(combined_previews, ignore_index=True) if combined_previews else primary_preview
    return build_success_result(
        spec=spec,
        summary=summary,
        explanation=explanation,
        data_preview=combined_preview,
        chart_bytes=primary_png,
        vega_spec=primary_vega,
        files=_files_as_strings(primary_paths),
        secondary_views=secondary_views,
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

        if fixed_spec.get("evidence_pattern") == "cross_dataset_comparison":
            return _run_cross_dataset_comparison(query, fixed_spec, paths)

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
