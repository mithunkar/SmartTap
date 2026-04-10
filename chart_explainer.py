
"""
chart_explainer.py
------------------
Generates plain-English explanations of SmartTap charts and summaries
using a local Ollama model.

This version grounds the explanation using:
- spec metadata
- dataframe-derived statistics
- Vega/Vega-Lite chart metadata
- optional categorical rows for crop summaries
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pandas as pd
import requests


VAR_DESCRIPTIONS = {
    "OBM": "average daily temperature (°F)",
    "MX": "maximum daily temperature (°F)",
    "MN": "minimum daily temperature (°F)",
    "PC": "daily precipitation (mm)",
    "SR": "solar radiation (Langleys)",
    "WS": "wind speed (mph)",
    "TU": "relative humidity (%)",
    "ET": "evapotranspiration (mm)",
    "ETa": "actual evapotranspiration (inches)",
    "PPT": "total precipitation (inches)",
    "AW": "applied water (acre-ft)",
    "WS_C": "water stress coefficient",
    "P_rz": "root-zone precipitation (inches)",
    "AREA": "total farmland area (acres)",
    "CROP": "number of crop fields",
    "IRR_STATUS": "irrigated field count",
    "per_IRRIGATED": "share of irrigated fields (%)",
    "IRR_EFF": "irrigation efficiency",
    "ITYPE": "irrigation system type",
}


def _describe_variable(var_name: str) -> str:
    return VAR_DESCRIPTIONS.get(var_name, var_name)


def _describe_variables(variables: List[str]) -> List[str]:
    return [f"{v} ({_describe_variable(v)})" for v in variables]


def _infer_trend(series: pd.Series) -> str:
    series = series.dropna()
    if len(series) < 6:
        return "insufficient data to determine trend"

    third = max(1, len(series) // 3)
    early_avg = float(series.iloc[:third].mean())
    late_avg = float(series.iloc[-third:].mean())
    diff = late_avg - early_avg

    if abs(diff) < 0.5:
        return "relatively stable"
    if diff > 0:
        return "generally increasing"
    return "generally decreasing"


def _quick_numeric_stats(df: pd.DataFrame, variables: List[str]) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}

    for v in variables:
        if v not in df.columns:
            continue

        series = df[v]
        if not pd.api.types.is_numeric_dtype(series):
            continue

        clean = series.dropna()
        if clean.empty:
            continue

        stats[v] = {
            "label": _describe_variable(v),
            "count": int(clean.count()),
            "mean": round(float(clean.mean()), 3),
            "median": round(float(clean.median()), 3),
            "min": round(float(clean.min()), 3),
            "max": round(float(clean.max()), 3),
            "trend": _infer_trend(clean),
        }

    return stats


def _categorical_summary(df: pd.DataFrame) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}

    if {"Crop", "Field Count"}.issubset(df.columns):
        crop_df = df[["Crop", "Field Count"]].copy()
        crop_df = crop_df.sort_values("Field Count", ascending=False)

        summary["top_categories"] = crop_df.head(5).to_dict(orient="records")
        summary["bottom_categories"] = crop_df.tail(3).to_dict(orient="records")
        summary["category_count"] = int(len(crop_df))

        if not crop_df.empty:
            top_row = crop_df.iloc[0]
            summary["dominant_category"] = {
                "name": top_row["Crop"],
                "value": int(top_row["Field Count"]),
            }

    return summary


def _extract_chart_metadata(vega_spec: Dict[str, Any] | None) -> Dict[str, Any]:
    if not vega_spec:
        return {}

    encoding = vega_spec.get("encoding", {})
    mark = vega_spec.get("mark", "")

    if isinstance(mark, dict):
        chart_type = mark.get("type", "")
    else:
        chart_type = mark

    x_enc = encoding.get("x", {}) if isinstance(encoding.get("x"), dict) else {}
    y_enc = encoding.get("y", {}) if isinstance(encoding.get("y"), dict) else {}
    color_enc = encoding.get("color", {}) if isinstance(encoding.get("color"), dict) else {}

    return {
        "title": vega_spec.get("title", ""),
        "chart_type": chart_type,
        "x_axis_field": x_enc.get("field"),
        "x_axis_title": x_enc.get("title"),
        "x_axis_type": x_enc.get("type"),
        "y_axis_field": y_enc.get("field"),
        "y_axis_title": y_enc.get("title"),
        "y_axis_type": y_enc.get("type"),
        "color_field": color_enc.get("field"),
        "color_title": color_enc.get("title"),
    }


def _sample_records(df: pd.DataFrame | None, limit: int = 5) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    sample = df.head(limit).copy()
    for col in sample.columns:
        if pd.api.types.is_datetime64_any_dtype(sample[col]):
            sample[col] = sample[col].astype(str)

    return sample.to_dict(orient="records")


def _build_explanation_context(
    spec: Dict[str, Any],
    df: pd.DataFrame | None = None,
    variables: List[str] | None = None,
    crop_rows: list | None = None,
    task: str | None = None,
    vega_spec: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    resolved_task = task or spec.get("task", "visualize_timeseries")
    resolved_vars = variables or spec.get("variables") or []

    context: Dict[str, Any] = {
        "task": resolved_task,
        "dataset": spec.get("dataset"),
        "location": spec.get("location"),
        "location_type": spec.get("location_type"),
        "start_date": spec.get("start_date"),
        "end_date": spec.get("end_date"),
        "year": spec.get("year"),
        "aggregation": spec.get("aggregation"),
        "variables": resolved_vars,
        "variable_labels": _describe_variables(resolved_vars),
    }

    context["chart_metadata"] = _extract_chart_metadata(vega_spec)

    if df is not None:
        context["row_count"] = int(len(df))
        context["column_names"] = list(df.columns)
        context["sample_records"] = _sample_records(df)
        context["numeric_summary"] = _quick_numeric_stats(df, resolved_vars)
        context["categorical_summary"] = _categorical_summary(df)
    else:
        context["row_count"] = 0
        context["column_names"] = []
        context["sample_records"] = []
        context["numeric_summary"] = {}
        context["categorical_summary"] = {}

    if crop_rows:
        context["top_category_rows"] = crop_rows[:10]

    return context


def _build_prompt_from_context(context: Dict[str, Any]) -> str:
    return f"""
You are explaining an agricultural data result to a non-technical user.

Use only the information provided in the context below.
Do not invent details.
Do not guess.
Do not introduce unrelated topics.

Instructions:
1. Start by saying what this result is about.
2. If it is a graph, mention what the x-axis and y-axis represent using the chart metadata.
3. If it is a categorical/bar chart, explain the most common and least common categories.
4. If it is a time series, explain the overall trend and notable highs/lows.
5. If it is a statistical summary, explain what the main numbers mean simply.
6. Keep the explanation factual, simple, and relevant to agriculture/weather/water data only.
7. Keep it to 3 to 5 sentences.

Context:
{json.dumps(context, indent=2, default=str)}
""".strip()


def _call_ollama(prompt: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:latest")

    response = requests.post(
        ollama_url,
        json={
            "model": ollama_model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=100,
    )
    response.raise_for_status()

    data = response.json()
    return data.get("response", "").strip()


def generate_chart_explanation(
    spec: Dict[str, Any],
    df: pd.DataFrame | None = None,
    variables: List[str] | None = None,
    crop_rows: list | None = None,
    task: str | None = None,
    vega_spec: Dict[str, Any] | None = None,
) -> str:
    context = _build_explanation_context(
        spec=spec,
        df=df,
        variables=variables,
        crop_rows=crop_rows,
        task=task,
        vega_spec=vega_spec,
    )

    prompt = _build_prompt_from_context(context)

    try:
        explanation = _call_ollama(prompt)
        return explanation if explanation else "Chart explanation could not be generated."
    except Exception as exc:
        return f"(Explanation unavailable: {exc})"

