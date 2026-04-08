from __future__ import annotations

import pandas as pd

from core.contracts import build_error_result, build_preview, build_success_result
from core.contracts import build_clarification_result
from core.data_fetcher import get_dataset_adapter
from core.validation import validate_and_fix_spec


def test_build_preview_keeps_small_frames_intact():
    df = pd.DataFrame({"value": [1, 2, 3]}, index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    preview = build_preview(df, limit=20)
    assert len(preview) == 3
    assert "index" in preview.columns or "datetime" in preview.columns


def test_build_preview_truncates_with_head_and_tail():
    df = pd.DataFrame({"value": list(range(30))}, index=pd.date_range("2024-01-01", periods=30, freq="D"))
    preview = build_preview(df, limit=20)
    assert len(preview) == 20
    assert preview["value"].iloc[0] == 0
    assert preview["value"].iloc[-1] == 29


def test_build_success_result_uses_canonical_shape():
    preview = pd.DataFrame({"value": [1]})
    result = build_success_result(
        spec={"task": "visualize_timeseries", "dataset": "agrimet"},
        summary={"row_count": 1},
        data_preview=preview,
        chart_bytes=b"png",
        vega_spec={"mark": "line"},
        files={"png": "outputs/charts/example.png"},
        validation_report={"ok": True},
    )
    assert result["success"] is True
    assert result["error"] is None
    assert result["data"] is preview
    assert result["files"]["png"].endswith(".png")


def test_build_error_result_uses_canonical_shape():
    result = build_error_result("boom")
    assert result["success"] is False
    assert result["error"] == "boom"
    assert result["spec"] is None
    assert result["files"] == {}


def test_build_clarification_result_uses_canonical_shape():
    result = build_clarification_result(
        spec={"task": "visualize_timeseries", "clarification_needed": ["location"]},
        prompt="Need location",
        fields=["location"],
    )
    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert result["clarification_prompt"] == "Need location"
    assert result["clarification_fields"] == ["location"]


def test_validate_and_fix_spec_normalizes_queryspec_shape():
    result = validate_and_fix_spec(
        {
            "dataset": "AGRIMET",
            "location": " Corvallis ",
            "variables": [" OBM ", " "],
            "statistics": [" MEAN "],
            "chart_type": "LINE",
        },
        "Show temperature in Corvallis for 2024",
    )
    assert result["dataset"] == "agrimet"
    assert result["location"] == "Corvallis"
    assert result["variables"] == ["OBM"]
    assert result["statistics"] == ["mean"]
    assert result["chart_type"] == "line"


def test_get_dataset_adapter_exposes_contract_defaults():
    adapter = get_dataset_adapter("openet")
    assert adapter.contract.name == "openet"
    assert adapter.contract.default_interval == "monthly"


def test_validate_and_fix_spec_drops_unmentioned_parser_location():
    result = validate_and_fix_spec(
        {
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "location": "corvallis",
            "variables": ["PC"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "show me precipitation in 2024",
    )
    assert "location" not in result
    assert "location" in result["clarification_needed"]
    assert any("Dropped parser-supplied location" in note for note in result["notes"])


def test_validate_and_fix_spec_drops_unmentioned_parser_time_range():
    result = validate_and_fix_spec(
        {
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "variables": ["PC"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "show me precipitation",
    )
    assert "start_date" not in result
    assert "end_date" not in result
    assert "time_range" in result["clarification_needed"]
    assert any("Dropped parser-supplied time range" in note for note in result["notes"])
