from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Protocol, Sequence, TypedDict

import pandas as pd


TaskName = Literal["visualize_timeseries", "statistical_summary", "summarize_crops"]
DatasetName = Literal["agrimet", "openet"]
LocationType = Literal["city", "county", "station"]


class QuerySpec(TypedDict, total=False):
    """Canonical resolved query contract shared across pipeline stages."""

    task: TaskName
    dataset: DatasetName
    location: str
    location_type: LocationType
    station_id: str
    variables: List[str]
    start_date: str
    end_date: str
    year: int
    interval: str
    chart_type: str
    aggregation: str
    statistics: List[str]
    crop_filter: str
    openet_geo: str
    openet_id: str
    huc8_code: str
    clarification_needed: List[str]
    confirmed_fields: List[str]
    notes: List[str]


class VisualizationFiles(TypedDict, total=False):
    png: str
    vega: str
    validation: str


class VisualizationResult(TypedDict):
    """Canonical UI/service output contract for successful and failed runs."""

    success: bool
    needs_clarification: bool
    error: str | None
    spec: QuerySpec | None
    summary: Dict[str, Any]
    data_preview: pd.DataFrame | None
    data: pd.DataFrame | None
    chart_bytes: bytes | None
    vega_spec: Dict[str, Any] | None
    files: VisualizationFiles
    validation_report: Dict[str, Any] | None
    clarification_prompt: str | None
    clarification_fields: List[str]


@dataclass(frozen=True)
class DatasetContract:
    """High-level capabilities each dataset adapter should declare."""

    name: str
    location_kinds: Sequence[str]
    default_interval: str
    supported_variables: Sequence[str] = field(default_factory=tuple)
    notes: str = ""


class DatasetAdapter(Protocol):
    """
    Target adapter boundary for dataset-specific behavior.

    Adapters own variable support, location resolution, and data retrieval.
    The service layer owns orchestration, validation, and result shaping.
    """

    contract: DatasetContract

    def fetch(self, spec: QuerySpec) -> Dict[str, Any]:
        """Return payload with keys: spec and data.records."""


def build_preview(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Keep previews readable while preserving head and tail context."""
    preview = df.reset_index()
    if len(preview) <= limit:
        return preview

    head_count = limit // 2
    tail_count = limit - head_count
    return pd.concat([preview.head(head_count), preview.tail(tail_count)], ignore_index=True)


def build_success_result(
    *,
    spec: QuerySpec,
    summary: Dict[str, Any],
    data_preview: pd.DataFrame,
    chart_bytes: bytes,
    vega_spec: Dict[str, Any],
    files: VisualizationFiles,
    validation_report: Dict[str, Any] | None = None,
) -> VisualizationResult:
    return {
        "success": True,
        "needs_clarification": False,
        "error": None,
        "spec": spec,
        "summary": summary,
        "data_preview": data_preview,
        "data": data_preview,
        "chart_bytes": chart_bytes,
        "vega_spec": vega_spec,
        "files": files,
        "validation_report": validation_report,
        "clarification_prompt": None,
        "clarification_fields": [],
    }


def build_error_result(message: str) -> VisualizationResult:
    return {
        "success": False,
        "needs_clarification": False,
        "error": message,
        "spec": None,
        "summary": {},
        "data_preview": None,
        "data": None,
        "chart_bytes": None,
        "vega_spec": None,
        "files": {},
        "validation_report": None,
        "clarification_prompt": None,
        "clarification_fields": [],
    }


def build_clarification_result(
    *,
    spec: QuerySpec,
    prompt: str,
    fields: List[str],
) -> VisualizationResult:
    return {
        "success": False,
        "needs_clarification": True,
        "error": None,
        "spec": spec,
        "summary": {"status": "clarification_needed"},
        "data_preview": None,
        "data": None,
        "chart_bytes": None,
        "vega_spec": None,
        "files": {},
        "validation_report": None,
        "clarification_prompt": prompt,
        "clarification_fields": fields,
    }
