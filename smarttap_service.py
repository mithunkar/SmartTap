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
    build_confirmation_result,
    build_error_result,
    build_preview,
    build_success_result,
)
from core.data_fetcher import fetch_data, fetch_grouped_data, supported_agrimet_locations
from core.location_crop_query import LocationCropQuery
from core.validation import validate_and_fix_spec, validate_payload
from core.explanation import build_result_explanation
from core.variable_registry import AGRIMET_VARIABLES, OPENET_VARIABLES, variable_label
from core.visualizer import (
    create_crop_bar_chart,
    create_crop_pie_chart,
    create_grouped_comparison_chart,
    create_grouped_summary_chart,
    payload_to_df,
    png_bytes,
    vega_spec,
)
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


def _write_text(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")


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
    label = variable_label(variable)
    values = [
        {"stat": "Mean", "value": stats["mean"]},
        {"stat": "Median", "value": stats["median"]},
        {"stat": "Min", "value": stats["min"]},
        {"stat": "Max", "value": stats["max"]},
    ]
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": f"{label} statistical summary",
        "data": {"values": values},
        "mark": "bar",
        "encoding": {
            "x": {"field": "stat", "type": "nominal", "title": "Statistic"},
            "y": {"field": "value", "type": "quantitative", "title": label},
            "tooltip": [
                {"field": "stat", "type": "nominal"},
                {"field": "value", "type": "quantitative"},
            ],
        },
    }


def _build_stat_png(variable: str, stats: Dict[str, float]) -> bytes:
    label = variable_label(variable)
    labels = ["Mean", "Median", "Min", "Max"]
    values = [stats["mean"], stats["median"], stats["min"], stats["max"]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, values, color="#b85c38")
    ax.set_title(f"{label} statistical summary")
    ax.set_ylabel(label)
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


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return cleaned or "query"


def _resolved_display_location(spec: Dict[str, Any]) -> str:
    return str(spec.get("display_location") or spec.get("location") or "the selected location")


def _exact_date_range(spec: Dict[str, Any], df: pd.DataFrame | None = None) -> str:
    if df is not None and not df.empty:
        if "datetime" in df.columns:
            values = pd.to_datetime(df["datetime"], errors="coerce").dropna()
        elif isinstance(df.index, pd.DatetimeIndex):
            values = pd.Series(df.index)
        else:
            values = pd.Series(dtype="datetime64[ns]")
        if not values.empty:
            return f"{values.min().date()} to {values.max().date()}"
    if spec.get("start_date") and spec.get("end_date"):
        return f"{spec['start_date']} to {spec['end_date']}"
    if spec.get("year"):
        return str(spec["year"])
    return ""


def _common_summary(spec: Dict[str, Any], variables: list[str], df: pd.DataFrame | None = None) -> Dict[str, Any]:
    source_datasets = list(spec.get("source_datasets") or ([spec.get("dataset")] if spec.get("dataset") else []))
    summary = {
        "task": spec.get("task"),
        "dataset": spec.get("dataset"),
        "location": _resolved_display_location(spec),
        "resolved_location": spec.get("location"),
        "location_type": spec.get("location_type"),
        "station_id": spec.get("station_id"),
        "station_title": spec.get("station_title"),
        "variables": ", ".join(variables),
        "variables_list": variables,
        "variable_labels": [variable_label(value) for value in variables],
        "date_range": _exact_date_range(spec, df),
        "source_datasets": source_datasets,
    }
    _set_optional(summary, "crop_filter", spec.get("crop_filter"))
    return summary


def _result_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if "datetime" in df.columns:
        return df.reset_index(drop=True)
    if isinstance(df.index, pd.DatetimeIndex):
        return df.reset_index()
    return df.reset_index(drop=True)


def _partner_results_paths(case_id: str) -> Dict[str, Path]:
    root = Path("results") / "partner_queries" / case_id
    root.mkdir(parents=True, exist_ok=True)
    return {
        "results_dir": root,
        "prompt": root / "prompt.txt",
        "resolved_query": root / "resolved_query.json",
        "data": root / "data.csv",
        "png": root / "chart.png",
        "vega": root / "vega.json",
        "validation": root / "validation.json",
        "verification": root / "verification.md",
    }


def _verification_template(query: str, result: Dict[str, Any]) -> str:
    spec = result.get("spec") or {}
    summary = result.get("summary") or {}
    lines = [
        "# Verification Notes",
        "",
        f"- Prompt: {query}",
        f"- Display location: {_resolved_display_location(spec)}",
        f"- Variables: {', '.join(summary.get('variable_labels') or [])}",
        f"- Date range: {summary.get('date_range') or ''}",
        f"- Source datasets: {', '.join(summary.get('source_datasets') or [])}",
        "",
        "## Todd/Tarkan Review",
        "",
        "- Data matches expected query: ",
        "- Chart looks correct: ",
        "- Follow-up notes: ",
        "",
    ]
    return "\n".join(lines)


def _save_partner_results(query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("success") or not result.get("spec"):
        return result

    spec = result["spec"]
    case_id = str(spec.get("partner_query_id") or _slugify(query))
    paths = _partner_results_paths(case_id)
    _write_text(paths["prompt"], query)
    _save_json(paths["resolved_query"], {"prompt": query, "spec": spec, "summary": result.get("summary") or {}})

    data = result.get("data")
    if isinstance(data, pd.DataFrame):
        _result_dataframe(data).to_csv(paths["data"], index=False)
    if result.get("chart_bytes"):
        _save_bytes(paths["png"], result["chart_bytes"])
    if result.get("vega_spec") is not None:
        _save_json(paths["vega"], result["vega_spec"])
    if result.get("validation_report") is not None:
        _save_json(paths["validation"], result["validation_report"])
    _write_text(paths["verification"], _verification_template(query, result))

    files = dict(result.get("files") or {})
    files.update(
        {
            "results_dir": str(paths["results_dir"]),
            "prompt": str(paths["prompt"]),
            "resolved_query": str(paths["resolved_query"]),
            "data": str(paths["data"]),
            "verification": str(paths["verification"]),
            "png": str(paths["png"]),
            "vega": str(paths["vega"]),
            "validation": str(paths["validation"]),
        }
    )
    result["files"] = files
    return result


def _set_optional(summary: Dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        summary[key] = value


def _resolved_request_text(spec: Dict[str, Any]) -> str:
    parts = []
    variables = spec.get("variables") or []
    if variables:
        labels = ", ".join(variable_label(variable) for variable in variables)
        parts.append(f"variables={labels}")
    if _resolved_display_location(spec):
        parts.append(f"location={_resolved_display_location(spec)}")
    if spec.get("station_title") or spec.get("station_id"):
        station_bits = " ".join(value for value in [spec.get("station_title"), f"({spec.get('station_id')})" if spec.get("station_id") else ""] if value)
        parts.append(f"station={station_bits}")
    date_range = _exact_date_range(spec)
    if date_range:
        parts.append(f"date_range={date_range}")
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


def _build_confirmation_prompt(spec: Dict[str, Any]) -> str:
    details = [
        f"Variables: {', '.join(variable_label(value) for value in spec.get('variables') or [])}",
        f"Location: {_resolved_display_location(spec)}",
    ]
    if spec.get("station_title") or spec.get("station_id"):
        station_bits = " ".join(value for value in [spec.get("station_title"), f"({spec.get('station_id')})" if spec.get("station_id") else ""] if value)
        details.append(f"Station: {station_bits}")
    if spec.get("source_datasets"):
        details.append(f"Sources: {', '.join(spec.get('source_datasets') or [])}")
    date_range = _exact_date_range(spec)
    if date_range:
        details.append(f"Time range: {date_range}")
    if spec.get("crop_filter"):
        details.append(f"Crop filter: {spec['crop_filter']}")
    return "Confirm this resolved request before SmartTap runs it:\n- " + "\n- ".join(details)


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
        merged["display_location"] = location
        clarified.add("location")
        missing = [field for field in missing if field not in {"location", "station"}]

    date_patch = _extract_date_patch(followup_query)
    if date_patch and "time_range" in missing:
        merged.update(date_patch)
        clarified.add("time_range")
        missing = [field for field in missing if field != "time_range"]

    merged["confirmed_fields"] = sorted(clarified)
    merged["confirmation_status"] = "pending"
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

    summary = _common_summary(final_spec, variables, _result_dataframe(df))
    summary.update(
        {
            "row_count": len(df),
            "evidence_pattern": final_spec.get("evidence_pattern"),
            "chart_package": final_spec.get("chart_package"),
        }
    )

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
        data=_result_dataframe(df),
        chart_bytes=png,
        vega_spec=vega,
        files=_files_as_strings(paths),
        secondary_views=secondary_views,
        validation_report=report,
    )


def _run_grouped_comparison(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    del query
    payload = fetch_grouped_data(spec)
    report = validate_payload(payload)
    _save_json(paths["validation"], report)
    if not report["ok"]:
        raise SmartTapError("; ".join(report["errors"]))

    final_spec = payload["spec"]
    records = (payload.get("data") or {}).get("records") or []
    if not records:
        raise SmartTapError("Grouped comparison returned no records.")

    df = pd.DataFrame.from_records(records)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"])
    if df.empty:
        raise SmartTapError("Grouped comparison returned no valid dated rows.")

    compare_by = str(final_spec.get("compare_by") or final_spec.get("split_by") or "")
    variables = sorted(df["variable"].astype(str).unique().tolist())
    primary_png, primary_vega = create_grouped_comparison_chart(
        df,
        location=_resolved_display_location(final_spec),
        compare_by=compare_by,
        variables=variables,
    )
    _save_bytes(paths["png"], primary_png)
    _save_json(paths["vega"], primary_vega)

    summary_df, summary_png, summary_vega = create_grouped_summary_chart(
        df,
        compare_by=compare_by,
        aggregation=str(final_spec.get("aggregation") or "mean"),
    )
    secondary_paths = _paths_with_suffix(paths, "grouped_summary")
    secondary_views = [
        _build_secondary_view(
            caption="This companion chart summarizes the grouped comparison across the selected categories.",
            chart_bytes=summary_png,
            vega=summary_vega,
            data_preview=summary_df,
            paths=secondary_paths,
        )
    ]

    result_df = df[["datetime", "group", "variable", "value"]].sort_values(["datetime", "group", "variable"]).reset_index(drop=True)
    preview = build_preview(result_df)
    summary = _common_summary(final_spec, variables, result_df)
    summary.update(
        {
            "row_count": len(df),
            "group_count": int(df["group"].nunique()),
            "groups": ", ".join(sorted(df["group"].astype(str).unique().tolist())),
            "compare_by": compare_by,
            "evidence_pattern": final_spec.get("evidence_pattern"),
            "chart_package": final_spec.get("chart_package"),
            "secondary_view_count": len(secondary_views),
        }
    )

    explanation = build_result_explanation(
        spec=final_spec,
        df=df,
        summary=summary,
        vega_spec=primary_vega,
    )

    return build_success_result(
        spec=final_spec,
        summary=summary,
        explanation=explanation,
        data_preview=preview,
        data=result_df,
        chart_bytes=primary_png,
        vega_spec=primary_vega,
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

    result_df = _result_dataframe(df)
    preview = build_preview(df)
    summary = _common_summary(final_spec, [variable], result_df)
    summary.update(
        {
            "variable": variable,
            "evidence_pattern": final_spec.get("evidence_pattern"),
            "chart_package": final_spec.get("chart_package"),
            **stats,
        }
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
        data=result_df,
        chart_bytes=png,
        vega_spec=vega,
        files=_files_as_strings(paths),
        secondary_views=[],
        validation_report=report,
    )


def _run_crop_summary(spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    query_system = _init_location_query()
    location = spec.get("location", "")
    display_location = _resolved_display_location(spec)
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
        raise SmartTapError(f"No crop data found for {display_location}.")

    crop_summary = (
        df.groupby(["crop_name", "crop_group"])
        .agg({"OPENET_ID": "count"})
        .reset_index()
        .rename(columns={"crop_name": "Crop", "crop_group": "Group", "OPENET_ID": "Field Count"})
        .sort_values("Field Count", ascending=False)
    )

    png, vega = create_crop_bar_chart(crop_summary, display_location, year, top_n=15)
    _save_bytes(paths["png"], png)
    _save_json(paths["vega"], vega)
    secondary_views = []

    if spec.get("evidence_pattern") in {"ranking_categories", "distribution_categories"}:
        secondary_paths = _paths_with_suffix(paths, "distribution")
        pie_png, pie_vega = create_crop_pie_chart(crop_summary, display_location, year, top_n=10)
        secondary_views.append(
            _build_secondary_view(
                caption="This companion chart shows the crop-group mix for the same location and year.",
                chart_bytes=pie_png,
                vega=pie_vega,
                data_preview=crop_summary.groupby("Group", as_index=False)["Field Count"].sum(),
                paths=secondary_paths,
            )
        )

    summary = _common_summary(spec, list(spec.get("variables") or ["CROP"]), crop_summary)
    summary.update(
        {
            "location_type": location_type,
            "year": year,
            "total_fields": int(len(df)),
            "total_crops": int(len(crop_summary)),
            "evidence_pattern": spec.get("evidence_pattern"),
            "chart_package": spec.get("chart_package"),
        }
    )

    explanation = build_result_explanation(
        spec=spec,
        df=crop_summary,
        summary=summary,
        vega_spec=vega,
    )

    validation_report = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "summary": {
            "row_count": int(len(crop_summary)),
            "field_count": int(len(df)),
        },
        "location": display_location,
        "variables": list(spec.get("variables") or ["CROP"]),
        "year": year,
    }

    return build_success_result(
        spec=spec,
        summary=summary,
        explanation=explanation,
        data_preview=crop_summary.head(20).reset_index(drop=True),
        data=crop_summary.reset_index(drop=True),
        chart_bytes=png,
        vega_spec=vega,
        files=_files_as_strings(paths),
        secondary_views=secondary_views,
        validation_report=validation_report,
    )


def _run_cross_dataset_comparison(query: str, spec: Dict[str, Any], paths: Dict[str, Path]) -> Dict[str, Any]:
    del query
    source_datasets = list(spec.get("source_datasets") or [])
    variables = list(spec.get("variables") or [])
    dataset_payloads = []
    combined_previews = []
    validation_reports: Dict[str, Any] = {}

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
        validation_reports[dataset] = report
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

    combined_preview = pd.concat(combined_previews, ignore_index=True) if combined_previews else primary_preview
    summary = _common_summary(spec, variables, combined_preview if not combined_preview.empty else _result_dataframe(primary_df))
    summary.update(
        {
            "dataset": primary_dataset,
            "row_count": sum(len(df) for _, _, df, _, _, _, _, _ in dataset_payloads),
            "evidence_pattern": spec.get("evidence_pattern"),
            "chart_package": spec.get("chart_package"),
            "secondary_view_count": len(secondary_views),
        }
    )

    explanation = build_result_explanation(
        spec=spec,
        df=primary_df,
        summary=summary,
        vega_spec=primary_vega,
    )

    validation_report = {
        "ok": all(report.get("ok", False) for report in validation_reports.values()),
        "errors": [
            error
            for report in validation_reports.values()
            for error in report.get("errors", [])
        ],
        "warnings": [
            warning
            for report in validation_reports.values()
            for warning in report.get("warnings", [])
        ],
        "datasets": validation_reports,
    }

    return build_success_result(
        spec=spec,
        summary=summary,
        explanation=explanation,
        data_preview=combined_preview,
        data=combined_preview,
        chart_bytes=primary_png,
        vega_spec=primary_vega,
        files=_files_as_strings(primary_paths),
        secondary_views=secondary_views,
        validation_report=validation_report,
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

        if fixed_spec.get("confirmation_status") != "confirmed":
            fixed_spec["confirmation_status"] = "pending"
            return build_confirmation_result(
                spec=fixed_spec,
                prompt=_build_confirmation_prompt(fixed_spec),
            )

        task = fixed_spec["task"]
        paths = _output_paths(_base_name())

        if fixed_spec.get("evidence_pattern") == "cross_dataset_comparison":
            return _save_partner_results(query, _run_cross_dataset_comparison(query, fixed_spec, paths))

        if fixed_spec.get("evidence_pattern") == "comparison_grouped":
            return _save_partner_results(query, _run_grouped_comparison(query, fixed_spec, paths))

        if task == "visualize_timeseries":
            return _save_partner_results(query, _run_visualization_task(query, fixed_spec, paths))
        if task == "statistical_summary":
            return _save_partner_results(query, _run_statistical_summary(query, fixed_spec, paths))
        if task == "summarize_crops":
            return _save_partner_results(query, _run_crop_summary(fixed_spec, paths))

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


def confirm_query(
    *,
    pending_spec: Dict[str, Any],
    original_query: str,
) -> Dict[str, Any]:
    confirmed_spec = dict(pending_spec)
    confirmed_spec["confirmation_status"] = "confirmed"
    return process_query(original_query, spec=confirmed_spec)
