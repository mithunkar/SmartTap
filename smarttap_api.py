from __future__ import annotations

import base64
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.variable_registry import variable_label, variables_for_dataset
from smarttap_service import apply_confirmation_edit, confirm_query, process_followup_reply, process_query


class MetricOption(BaseModel):
    code: str
    label: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    metric_options: list[MetricOption]


class DataFramePayload(BaseModel):
    columns: list[str]
    records: list[dict[str, Any]]


class ChartSeriesPayload(BaseModel):
    key: str
    label: str
    color: str | None = None


class ChartModelPayload(BaseModel):
    kind: Literal["line", "bar", "pie", "donut"]
    title: str
    rows: list[dict[str, Any]]
    x_key: str
    x_label: str | None = None
    y_label: str | None = None
    series: list[ChartSeriesPayload]
    stacked: bool = False
    horizontal: bool = False
    value_format: str | None = None
    legend_title: str | None = None


class SecondaryViewPayload(BaseModel):
    caption: str = ""
    chart_image_url: str | None = None
    chart_model: ChartModelPayload | None = None
    vega_spec: dict[str, Any] | None = None
    data_preview: DataFramePayload | None = None
    files: dict[str, str] = Field(default_factory=dict)


class VisualizationResponse(BaseModel):
    success: bool
    needs_clarification: bool
    needs_confirmation: bool
    error: str | None
    spec: dict[str, Any] | None
    summary: dict[str, Any]
    explanation: str
    data_preview: DataFramePayload | None
    data: DataFramePayload | None
    chart_image_url: str | None
    chart_model: ChartModelPayload | None
    vega_spec: dict[str, Any] | None
    secondary_views: list[SecondaryViewPayload]
    files: dict[str, str]
    validation_report: dict[str, Any] | None
    clarification_prompt: str | None
    confirmation_prompt: str | None
    clarification_fields: list[str]


class QueryRequest(BaseModel):
    query: str
    spec: dict[str, Any] | None = None


class FollowupRequest(BaseModel):
    followup_query: str
    pending_spec: dict[str, Any]
    original_query: str


class ConfirmationEditRequest(BaseModel):
    pending_spec: dict[str, Any]
    original_query: str
    field: Literal["crop", "location", "time_range", "metric"]
    value: Any


class ConfirmationConfirmRequest(BaseModel):
    pending_spec: dict[str, Any]
    original_query: str


def _metric_options() -> list[MetricOption]:
    seen: set[str] = set()
    options: list[MetricOption] = []
    for dataset in ["agrimet", "openet"]:
        for metadata in variables_for_dataset(dataset):
            if metadata.code in seen:
                continue
            seen.add(metadata.code)
            options.append(MetricOption(code=metadata.code, label=variable_label(metadata.code)))
    return options


def _to_data_url(payload: bytes | None, mime_type: str = "image/png") -> str | None:
    if not payload:
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _jsonable_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if pd.isna(value) else value
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return _jsonable_scalar(value.item())
        except Exception:
            pass
    return value


def to_jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return dataframe_payload(value).model_dump()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return _jsonable_scalar(value)


def dataframe_payload(df: pd.DataFrame | None) -> DataFramePayload | None:
    if df is None:
        return None
    safe_df = df.copy()
    records = [
        {str(column): to_jsonable(value) for column, value in row.items()}
        for row in safe_df.to_dict(orient="records")
    ]
    return DataFramePayload(columns=[str(column) for column in safe_df.columns], records=records)


def _mark_type(mark: Any) -> str:
    if isinstance(mark, str):
        return mark
    if isinstance(mark, dict):
        return str(mark.get("type") or "")
    return ""


def _legend_title(encoding: dict[str, Any]) -> str | None:
    color = encoding.get("color") or {}
    legend = color.get("legend") or {}
    title = legend.get("title") or color.get("title")
    return str(title) if title else None


def _pretty_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text == "datetime":
        return "Date/Time"
    if " • " in text:
        return " • ".join(_pretty_label(part) for part in text.split(" • "))
    variable_text = variable_label(text)
    if variable_text != text:
        return variable_text
    return text.replace("_", " ").title()


def _axis_label(channel: dict[str, Any], *, fallback_field: str | None = None) -> str | None:
    title = channel.get("title")
    if title:
        return str(title)
    field = channel.get("field") or fallback_field
    if field:
        return _pretty_label(field)
    return None


def _value_format(field_name: str) -> str | None:
    lowered = str(field_name or "").lower()
    if "percent" in lowered or lowered.startswith("per_") or "share" in lowered or "humidity" in lowered:
        return "percent"
    return None


def _series_color(index: int) -> str:
    palette = [
        "#4c78a8",
        "#f58518",
        "#54a24b",
        "#e45756",
        "#72b7b2",
        "#b279a2",
        "#ff9da6",
        "#9d755d",
        "#bab0ac",
    ]
    return palette[index % len(palette)]


def _wide_rows(
    values: list[dict[str, Any]],
    *,
    x_key: str,
    series_name_fn,
    value_field: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows_by_key: dict[Any, dict[str, Any]] = {}
    ordered_keys: list[Any] = []
    ordered_series: list[str] = []

    for value in values:
        x_value = to_jsonable(value.get(x_key))
        if x_value not in rows_by_key:
            rows_by_key[x_value] = {x_key: x_value}
            ordered_keys.append(x_value)
        series_name = str(series_name_fn(value))
        if series_name not in ordered_series:
            ordered_series.append(series_name)
        rows_by_key[x_value][series_name] = to_jsonable(value.get(value_field))

    return [rows_by_key[key] for key in ordered_keys], ordered_series


def chart_model_from_vega(vega_spec: dict[str, Any] | None) -> ChartModelPayload | None:
    if not isinstance(vega_spec, dict):
        return None

    title = str(vega_spec.get("title") or "")
    values = vega_spec.get("data", {}).get("values")
    if not isinstance(values, list) or not values:
        return None

    if "facet" in vega_spec and isinstance(vega_spec.get("spec"), dict):
        facet = vega_spec.get("facet") or {}
        inner = vega_spec.get("spec") or {}
        encoding = inner.get("encoding") or {}
        mark_type = _mark_type(inner.get("mark"))
        x_field = (encoding.get("x") or {}).get("field")
        y_field = (encoding.get("y") or {}).get("field")
        color_field = (encoding.get("color") or {}).get("field")
        facet_field = facet.get("field")
        if mark_type == "line" and x_field and y_field and color_field and facet_field:
            rows, series_names = _wide_rows(
                values,
                x_key=str(x_field),
                value_field=str(y_field),
                series_name_fn=lambda row: f"{_pretty_label(row.get(facet_field))} • {row.get(color_field)}",
            )
            return ChartModelPayload(
                kind="line",
                title=title,
                rows=rows,
                x_key=str(x_field),
                x_label=_axis_label(encoding.get("x") or {}),
                y_label=_axis_label(encoding.get("y") or {}),
                series=[
                    ChartSeriesPayload(key=name, label=name, color=_series_color(index))
                    for index, name in enumerate(series_names)
                ],
                legend_title=_legend_title(encoding),
                value_format=_value_format(str(y_field)),
            )
        return None

    encoding = vega_spec.get("encoding") or {}
    mark_type = _mark_type(vega_spec.get("mark"))
    x = encoding.get("x") or {}
    y = encoding.get("y") or {}
    color = encoding.get("color") or {}

    if mark_type == "arc":
        label_field = color.get("field")
        value_field = (encoding.get("theta") or {}).get("field")
        if not label_field or not value_field:
            return None
        kind = "donut" if isinstance(vega_spec.get("mark"), dict) and vega_spec["mark"].get("innerRadius") else "pie"
        return ChartModelPayload(
            kind=kind,
            title=title,
            rows=[to_jsonable(item) for item in values],
            x_key=str(label_field),
            x_label=_pretty_label(label_field),
            y_label=_axis_label(encoding.get("theta") or {}, fallback_field=str(value_field)),
            series=[
                ChartSeriesPayload(
                    key=str(value_field),
                    label=_axis_label(encoding.get("theta") or {}, fallback_field=str(value_field)) or str(value_field),
                    color=_series_color(0),
                )
            ],
            legend_title=_legend_title(encoding),
            value_format=_value_format(str(value_field)),
        )

    x_field = x.get("field")
    y_field = y.get("field")
    if not x_field or not y_field:
        return None

    if mark_type == "line":
        color_field = color.get("field")
        if color_field:
            rows, series_names = _wide_rows(
                values,
                x_key=str(x_field),
                value_field=str(y_field),
                series_name_fn=lambda row: (
                    _pretty_label(row.get(color_field)) if str(color_field) == "variable" else str(row.get(color_field))
                ),
            )
            return ChartModelPayload(
                kind="line",
                title=title,
                rows=rows,
                x_key=str(x_field),
                x_label=_axis_label(x),
                y_label=_axis_label(y),
                series=[
                    ChartSeriesPayload(key=name, label=name, color=_series_color(index))
                    for index, name in enumerate(series_names)
                ],
                legend_title=_legend_title(encoding),
                value_format=_value_format(str(y_field)),
            )

        return ChartModelPayload(
            kind="line",
            title=title,
            rows=[to_jsonable(item) for item in values],
            x_key=str(x_field),
            x_label=_axis_label(x),
            y_label=_axis_label(y),
            series=[
                ChartSeriesPayload(
                    key=str(y_field),
                    label=_axis_label(y, fallback_field=str(y_field)) or str(y_field),
                    color=_series_color(0),
                )
            ],
            value_format=_value_format(str(y_field)),
        )

    if mark_type == "bar":
        x_type = str(x.get("type") or "")
        y_type = str(y.get("type") or "")
        color_field = color.get("field")
        if x_type == "quantitative" and y_type == "nominal":
            return ChartModelPayload(
                kind="bar",
                title=title,
                rows=[to_jsonable(item) for item in values],
                x_key=str(y_field),
                x_label=_axis_label(y),
                y_label=_axis_label(x),
                series=[
                    ChartSeriesPayload(
                        key=str(x_field),
                        label=_axis_label(x, fallback_field=str(x_field)) or str(x_field),
                        color=_series_color(0),
                    )
                ],
                horizontal=True,
                legend_title=_legend_title(encoding),
                value_format=_value_format(str(x_field)),
            )

        if color_field:
            rows, series_names = _wide_rows(
                values,
                x_key=str(x_field),
                value_field=str(y_field),
                series_name_fn=lambda row: (
                    _pretty_label(row.get(color_field)) if str(color_field) == "variable" else str(row.get(color_field))
                ),
            )
            return ChartModelPayload(
                kind="bar",
                title=title,
                rows=rows,
                x_key=str(x_field),
                x_label=_axis_label(x),
                y_label=_axis_label(y),
                series=[
                    ChartSeriesPayload(key=name, label=name, color=_series_color(index))
                    for index, name in enumerate(series_names)
                ],
                stacked=str(y.get("stack") or "").lower() == "zero",
                legend_title=_legend_title(encoding),
                value_format=_value_format(str(y_field)),
            )

        return ChartModelPayload(
            kind="bar",
            title=title,
            rows=[to_jsonable(item) for item in values],
            x_key=str(x_field),
            x_label=_axis_label(x),
            y_label=_axis_label(y),
            series=[
                ChartSeriesPayload(
                    key=str(y_field),
                    label=_axis_label(y, fallback_field=str(y_field)) or str(y_field),
                    color=_series_color(0),
                )
            ],
            value_format=_value_format(str(y_field)),
        )

    return None


def serialize_visualization_result(result: dict[str, Any]) -> VisualizationResponse:
    secondary_views: list[SecondaryViewPayload] = []
    for view in result.get("secondary_views") or []:
        vega_spec = to_jsonable(view.get("vega_spec"))
        secondary_views.append(
            SecondaryViewPayload(
                caption=str(view.get("caption") or ""),
                chart_image_url=_to_data_url(view.get("chart_bytes")),
                chart_model=chart_model_from_vega(vega_spec),
                vega_spec=vega_spec,
                data_preview=dataframe_payload(view.get("data_preview")),
                files={str(key): str(value) for key, value in (view.get("files") or {}).items() if value},
            )
        )

    vega_spec = to_jsonable(result.get("vega_spec"))
    return VisualizationResponse(
        success=bool(result.get("success")),
        needs_clarification=bool(result.get("needs_clarification")),
        needs_confirmation=bool(result.get("needs_confirmation")),
        error=result.get("error"),
        spec=to_jsonable(result.get("spec")),
        summary=to_jsonable(result.get("summary") or {}),
        explanation=str(result.get("explanation") or ""),
        data_preview=dataframe_payload(result.get("data_preview")),
        data=dataframe_payload(result.get("data")),
        chart_image_url=_to_data_url(result.get("chart_bytes")),
        chart_model=chart_model_from_vega(vega_spec),
        vega_spec=vega_spec,
        secondary_views=secondary_views,
        files={str(key): str(value) for key, value in (result.get("files") or {}).items() if value},
        validation_report=to_jsonable(result.get("validation_report")),
        clarification_prompt=result.get("clarification_prompt"),
        confirmation_prompt=result.get("confirmation_prompt"),
        clarification_fields=[str(item) for item in (result.get("clarification_fields") or [])],
    )


app = FastAPI(title="SmartTap API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="smarttap-api",
        metric_options=_metric_options(),
    )


@app.post("/api/query", response_model=VisualizationResponse)
def post_query(payload: QueryRequest) -> VisualizationResponse:
    return serialize_visualization_result(process_query(payload.query, spec=payload.spec))


@app.post("/api/followup", response_model=VisualizationResponse)
def post_followup(payload: FollowupRequest) -> VisualizationResponse:
    return serialize_visualization_result(
        process_followup_reply(
            followup_query=payload.followup_query,
            pending_spec=payload.pending_spec,
            original_query=payload.original_query,
        )
    )


@app.post("/api/confirmation/edit", response_model=VisualizationResponse)
def post_confirmation_edit(payload: ConfirmationEditRequest) -> VisualizationResponse:
    return serialize_visualization_result(
        apply_confirmation_edit(
            pending_spec=payload.pending_spec,
            original_query=payload.original_query,
            field=payload.field,
            value=payload.value,
        )
    )


@app.post("/api/confirmation/confirm", response_model=VisualizationResponse)
def post_confirmation_confirm(payload: ConfirmationConfirmRequest) -> VisualizationResponse:
    return serialize_visualization_result(
        confirm_query(
            pending_spec=payload.pending_spec,
            original_query=payload.original_query,
        )
    )
