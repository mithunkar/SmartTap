from __future__ import annotations

import pandas as pd

from core.contracts import build_error_result, build_preview, build_success_result


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
