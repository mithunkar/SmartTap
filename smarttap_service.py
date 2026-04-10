from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

cache_dir = Path(__file__).resolve().parent / ".cache" / "matplotlib"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir.parent))

import matplotlib.pyplot as plt
import pandas as pd

from core.data_fetcher import fetch_data
from core.location_crop_query import LocationCropQuery
from core.validation import validate_and_fix_spec, validate_payload
from core.visualizer import create_crop_bar_chart, payload_to_df, png_bytes, vega_spec
from llm.interpretation import get_task_specification

# ── NEW: plain-English chart explanation ──────────────────────────────────────
from chart_explainer import generate_chart_explanation
# ─────────────────────────────────────────────────────────────────────────────


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


def _result_success(
    *,
    spec: Dict[str, Any],
    summary: Dict[str, Any],
    data_preview: pd.DataFrame,
    chart_bytes: bytes,
    vega: Dict[str, Any],
    files: Dict[str, str],
    explanation: str = "",                  # ← NEW
    validation_report: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "success": True,
        "spec": spec,
        "summary": summary,
        "data_preview": data_preview,
        "data": data_preview,
        "chart_bytes": chart_bytes,
        "vega_spec": vega,
        "files": files,
        "explanation": explanation,         # ← NEW
        "validation_report": validation_report,
    }


def _result_error(message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "error": message,
        "spec": None,
        "summary": {},
        "data_preview": None,
        "data": None,
        "chart_bytes": None,
        "vega_spec": None,
        "files": {},
        "explanation": "",                  # ← NEW (keeps key consistent)
    }


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
    preview = df.reset_index()
    if len(preview) > 20:
        preview = pd.concat([preview.head(10), preview.tail(10)], ignore_index=True)

    summary = {
        "task": final_spec["task"],
        "dataset": final_spec["dataset"],
        "location": final_spec.get("location"),
        "variables": ", ".join(variables),
        "row_count": len(df),
        "date_range": f"{final_spec.get('start_date')} to {final_spec.get('end_date')}",
    }

    # ── Generate plain-English explanation ───────────────────────────────────
    explanation = generate_chart_explanation(
        spec=final_spec,
        df=df,
        variables=variables,
        task="visualize_timeseries",
        vega_spec=vega,

    )
    # ─────────────────────────────────────────────────────────────────────────

    return _result_success(
        spec=final_spec,
        summary=summary,
        data_preview=preview,
        chart_bytes=png,
        vega=vega,
        files={key: str(value) for key, value in paths.items()},
        explanation=explanation,
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

    preview = df.reset_index().head(20)
    summary = {
        "task": final_spec["task"],
        "dataset": final_spec["dataset"],
        "location": final_spec.get("location"),
        "variable": variable,
        **stats,
    }

    # ── Generate plain-English explanation ───────────────────────────────────
    explanation = generate_chart_explanation(
        spec=final_spec,
        df=df,
        variables=[variable],
        task="statistical_summary",
        vega_spec=vega,
    )
    # ─────────────────────────────────────────────────────────────────────────

    return _result_success(
        spec=final_spec,
        summary=summary,
        data_preview=preview,
        chart_bytes=png,
        vega=vega,
        files={key: str(value) for key, value in paths.items()},
        explanation=explanation,
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

    # ── Generate plain-English explanation ───────────────────────────────────
    crop_rows = crop_summary.head(15).to_dict(orient="records")
    explanation = generate_chart_explanation(
        spec=spec,
        crop_rows=crop_rows,
        task="summarize_crops",
        vega_spec=vega,
    )
    # ─────────────────────────────────────────────────────────────────────────

    return _result_success(
        spec=spec,
        summary=summary,
        data_preview=crop_summary.head(20).reset_index(drop=True),
        chart_bytes=png,
        vega=vega,
        files={key: str(value) for key, value in paths.items()},
        explanation=explanation,
    )


def process_query(query: str, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        raw_spec = spec if spec is not None else get_task_specification(query)
        fixed_spec = validate_and_fix_spec(raw_spec, query)

        if fixed_spec.get("task") == "error":
            return _result_error(fixed_spec.get("error_message", "Invalid query."))

        task = fixed_spec["task"]
        paths = _output_paths(_base_name())

        if task == "visualize_timeseries":
            return _run_visualization_task(query, fixed_spec, paths)
        if task == "statistical_summary":
            return _run_statistical_summary(query, fixed_spec, paths)
        if task == "summarize_crops":
            return _run_crop_summary(fixed_spec, paths)

        return _result_error(f"Unsupported task: {task}")
    except SmartTapError as exc:
        return _result_error(str(exc))
    except Exception as exc:
        return _result_error(str(exc))
