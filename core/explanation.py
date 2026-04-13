from __future__ import annotations

from typing import Any, Callable, Dict, List

import pandas as pd

from .variable_registry import variable_label


ExplanationBuilder = Callable[[Dict[str, Any], pd.DataFrame | None, Dict[str, Any], Dict[str, Any] | None], str]


def _format_location(spec: Dict[str, Any]) -> str:
    location = spec.get("location")
    if not location:
        return "the selected location"
    return str(location)


def _format_date_range(spec: Dict[str, Any]) -> str:
    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    if start_date and end_date:
        return f"from {start_date} to {end_date}"
    if spec.get("year"):
        return f"in {spec['year']}"
    return ""


def _join_labels(variables: List[str]) -> str:
    labels = [variable_label(variable) for variable in variables]
    if not labels:
        return "the selected variable"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _extract_axis_titles(vega_spec: Dict[str, Any] | None) -> tuple[str, str]:
    if not vega_spec:
        return ("Date/Time", "Value")

    encoding = vega_spec.get("encoding", {})
    x_title = "Date/Time"
    y_title = "Value"
    if isinstance(encoding.get("x"), dict):
        x_title = str(encoding["x"].get("title") or encoding["x"].get("field") or x_title)
    if isinstance(encoding.get("y"), dict):
        y_title = str(encoding["y"].get("title") or encoding["y"].get("field") or y_title)
    return x_title, y_title


def _is_temporal_chart(vega_spec: Dict[str, Any] | None, df: pd.DataFrame | None) -> bool:
    if vega_spec:
        encoding = vega_spec.get("encoding", {})
        x_enc = encoding.get("x", {})
        if isinstance(x_enc, dict) and x_enc.get("type") == "temporal":
            return True
    if df is None:
        return False
    if isinstance(df.index, pd.DatetimeIndex):
        return True
    return "datetime" in df.columns and pd.api.types.is_datetime64_any_dtype(df["datetime"])


def _infer_trend(series: pd.Series) -> str | None:
    clean = series.dropna()
    if len(clean) < 6:
        return None

    third = max(1, len(clean) // 3)
    early_avg = float(clean.iloc[:third].mean())
    late_avg = float(clean.iloc[-third:].mean())
    diff = late_avg - early_avg
    spread = float(clean.max() - clean.min())
    threshold = max(spread * 0.1, 0.01)

    if abs(diff) <= threshold:
        return "relatively stable"
    if diff > 0:
        return "generally increasing"
    return "generally decreasing"


def _build_timeseries_explanation(
    spec: Dict[str, Any],
    df: pd.DataFrame | None,
    summary: Dict[str, Any],
    vega_spec: Dict[str, Any] | None,
) -> str:
    variables = list(spec.get("variables") or summary.get("variables_list") or [])
    label_text = _join_labels(variables)
    location = _format_location(spec)
    date_range = _format_date_range(spec)
    x_title, y_title = _extract_axis_titles(vega_spec)
    row_count = summary.get("row_count") or (len(df) if df is not None else 0)

    sentences = [
        f"This chart shows {label_text} for {location}{(' ' + date_range) if date_range else ''}.",
        f"The x-axis shows {x_title.lower()}, and the y-axis shows {y_title.lower()}.",
        f"It includes {row_count} plotted records that you can inspect in the data preview.",
    ]

    if (
        df is not None
        and _is_temporal_chart(vega_spec, df)
        and len(variables) == 1
        and variables[0] in df.columns
        and pd.api.types.is_numeric_dtype(df[variables[0]])
    ):
        series = df[variables[0]]
        trend = _infer_trend(series)
        clean = series.dropna()
        if trend and not clean.empty:
            sentences.append(
                f"Across the plotted period, {variable_label(variables[0])} is {trend}, ranging from {clean.min():.2f} to {clean.max():.2f}."
            )
    elif len(variables) > 1:
        sentences.append("Use the shared time axis to compare how the selected variables move over the same period.")

    return " ".join(sentences)


def _build_statistical_explanation(
    spec: Dict[str, Any],
    df: pd.DataFrame | None,
    summary: Dict[str, Any],
    vega_spec: Dict[str, Any] | None,
) -> str:
    del df, vega_spec
    variable = str(summary.get("variable") or (spec.get("variables") or ["the selected variable"])[0])
    label = variable_label(variable)
    location = _format_location(spec)
    count = summary.get("count", 0)
    mean = summary.get("mean")
    median = summary.get("median")
    minimum = summary.get("min")
    maximum = summary.get("max")

    return (
        f"This result summarizes {label} for {location}. "
        f"The chart compares the mean, median, minimum, and maximum across {count} records. "
        f"The average was {mean}, the median was {median}, the minimum was {minimum}, and the maximum was {maximum}."
    )


def _build_crop_summary_explanation(
    spec: Dict[str, Any],
    df: pd.DataFrame | None,
    summary: Dict[str, Any],
    vega_spec: Dict[str, Any] | None,
) -> str:
    del vega_spec
    location = _format_location(spec)
    year = summary.get("year") or spec.get("year")
    total_fields = summary.get("total_fields", 0)
    total_crops = summary.get("total_crops", 0)

    if df is None or df.empty:
        return f"This chart summarizes crop counts for {location}{f' in {year}' if year else ''}."

    top_row = df.iloc[0]
    top_crop = top_row.get("Crop", "the leading crop")
    top_count = top_row.get("Field Count", 0)

    return (
        f"This chart ranks crops for {location}{f' in {year}' if year else ''}. "
        f"The largest category shown is {top_crop} with {top_count} fields. "
        f"In total, the result covers {total_fields} fields across {total_crops} crop categories."
    )


EXPLANATION_BUILDERS: Dict[str, ExplanationBuilder] = {
    "visualize_timeseries": _build_timeseries_explanation,
    "statistical_summary": _build_statistical_explanation,
    "summarize_crops": _build_crop_summary_explanation,
}


def build_result_explanation(
    *,
    spec: Dict[str, Any],
    df: pd.DataFrame | None,
    summary: Dict[str, Any],
    vega_spec: Dict[str, Any] | None = None,
) -> str:
    task = str(spec.get("task") or summary.get("task") or "").strip()
    builder = EXPLANATION_BUILDERS.get(task)
    if builder is None:
        return ""
    return builder(spec, df, summary, vega_spec).strip()
