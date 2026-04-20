from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from smarttap_service import apply_confirmation_edit, confirm_query, process_clarification_reply, process_query


@pytest.fixture(autouse=True)
def _isolated_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _run_confirmed_query(query: str, spec: dict) -> tuple[dict, dict]:
    initial = process_query(query, spec=spec)
    assert initial["success"] is False
    assert initial["needs_confirmation"] is True

    final = confirm_query(
        pending_spec=initial["spec"],
        original_query=query,
    )
    assert final["success"] is True
    return initial, final


def _assert_partner_artifacts(result: dict) -> None:
    for key in ["results_dir", "prompt", "resolved_query", "data", "png", "vega", "validation", "verification"]:
        assert key in result["files"]
        assert Path(result["files"][key]).exists()


def test_visualize_timeseries_requires_confirmation_and_writes_partner_artifacts(monkeypatch):
    def fake_fetch_data(spec):
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "OBM": 40.0},
                    {"datetime": "2024-01-02", "OBM": 42.0},
                    {"datetime": "2024-01-03", "OBM": 44.0},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    query = "Show temperature in Corvallis for early 2024"
    spec = {
        "partner_query_id": "service_visualize_timeseries",
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "corvallis",
        "display_location": "Corvallis",
        "variables": ["OBM"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-03",
        "interval": "daily",
        "chart_type": "line",
    }

    initial, final = _run_confirmed_query(query, spec)

    assert "Average Temperature (deg F)" in initial["confirmation_prompt"]
    assert final["summary"]["dataset"] == "agrimet"
    assert final["summary"]["location"] == "Corvallis"
    assert final["summary"]["variable_labels"] == ["Average Temperature (deg F)"]
    assert final["summary"]["date_range"] == "2024-01-01 to 2024-01-03"
    assert final["spec"]["confirmation_status"] == "confirmed"
    _assert_partner_artifacts(final)


def test_statistical_summary_confirmation_then_success_has_no_trend_language(monkeypatch):
    def fake_fetch_data(spec):
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "ETa": 0.16},
                    {"datetime": "2024-02-01", "ETa": 1.25},
                    {"datetime": "2024-03-01", "ETa": 2.41},
                    {"datetime": "2024-04-01", "ETa": 3.18},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    _, final = _run_confirmed_query(
        "What is the average ETa in Hood River in 2024?",
        {
            "partner_query_id": "service_statistical_summary",
            "task": "statistical_summary",
            "dataset": "openet",
            "location": "Hood River",
            "location_type": "county",
            "variables": ["ETa"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
            "aggregation": "mean",
            "openet_geo": "location",
        },
    )

    explanation = final["explanation"].lower()
    assert "average" in explanation
    assert "median" in explanation
    assert "trend" not in explanation
    assert "increasing" not in explanation
    assert "decreasing" not in explanation
    _assert_partner_artifacts(final)


def test_crop_summary_confirmation_then_success(monkeypatch):
    class FakeLocationQuery:
        def query_crops_by_city(self, clean_location, year):
            assert clean_location == "Corvallis"
            assert year == 2024
            return pd.DataFrame(
                {
                    "crop_name": ["Alfalfa", "Alfalfa", "Corn"],
                    "crop_group": ["Hay", "Hay", "Grain"],
                    "OPENET_ID": [1, 2, 3],
                }
            )

    monkeypatch.setattr("smarttap_service._init_location_query", lambda: FakeLocationQuery())

    _, final = _run_confirmed_query(
        "What crops are grown in Corvallis?",
        {
            "partner_query_id": "service_crop_summary",
            "task": "summarize_crops",
            "location": "Corvallis",
            "location_type": "city",
            "year": 2024,
        },
    )

    assert final["summary"]["task"] == "summarize_crops"
    assert final["summary"]["total_fields"] == 3
    assert len(final["secondary_views"]) == 1
    assert "alfalfa" in final["explanation"].lower()
    _assert_partner_artifacts(final)


def test_morrow_alfalfa_natural_language_query_returns_yearly_openet_rows():
    query = "How has the amount of farmland planted with alfalfa changed in Morrow County between 2014 and 2022?"

    initial = process_query(query, spec={"partner_query_id": "service_morrow_alfalfa"})

    assert initial["success"] is False
    assert initial["needs_confirmation"] is True
    assert initial["spec"]["dataset"] == "openet"
    assert initial["spec"]["display_location"] == "Morrow County"
    assert initial["spec"]["variables"] == ["ACRES_FTR_GEOM"]
    assert initial["spec"]["crop_filter"] == "Alfalfa"

    final = confirm_query(
        pending_spec=initial["spec"],
        original_query=query,
    )

    assert final["success"] is True
    assert final["summary"]["dataset"] == "openet"
    assert final["summary"]["location"] == "Morrow County"
    assert len(final["data"]) == 9
    assert final["data"]["datetime"].min().strftime("%Y-%m-%d") == "2014-01-01"
    assert final["data"]["datetime"].max().strftime("%Y-%m-%d") == "2022-01-01"
    assert (final["data"]["ACRES_FTR_GEOM"] > 0).all()
    _assert_partner_artifacts(final)


def test_deschutes_potato_share_query_stays_a_trend_not_grouped_comparison():
    query = "How did the share of irrigated fields growing potatoes change in Deschutes County from 2018 to 2024?"

    initial = process_query(query, spec={"partner_query_id": "service_deschutes_potato"})

    assert initial["success"] is False
    assert initial["needs_confirmation"] is True
    assert initial["spec"]["variables"] == ["per_IRRIGATED"]
    assert initial["spec"]["crop_filter"] == "Potato"
    assert initial["spec"]["evidence_pattern"] == "trend_single"
    assert "compare_by" not in initial["spec"]
    assert "split_by" not in initial["spec"]
    assert "group_by" not in initial["spec"]

    final = confirm_query(
        pending_spec=initial["spec"],
        original_query=query,
    )

    assert final["success"] is True
    assert final["spec"]["evidence_pattern"] == "trend_single"
    assert "compare_by" not in final["spec"]
    assert "split_by" not in final["spec"]
    assert "group_by" not in final["spec"]
    assert len(final["data"]) >= 2
    assert final["data"]["datetime"].min().strftime("%Y-%m-%d") == "2018-01-01"
    assert final["data"]["datetime"].max().strftime("%Y-%m-%d") == "2024-01-01"
    _assert_partner_artifacts(final)


def test_parser_noise_with_crop_group_variable_normalizes_to_trend(monkeypatch):
    def fake_fetch_data(spec):
        assert spec["variables"] == ["per_IRRIGATED"]
        assert spec["evidence_pattern"] == "trend_single"
        assert "compare_by" not in spec
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2018-01-01", "per_IRRIGATED": 10.0},
                    {"datetime": "2019-01-01", "per_IRRIGATED": 12.5},
                    {"datetime": "2020-01-01", "per_IRRIGATED": 15.0},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    query = "How did the share of irrigated fields growing potatoes change in Deschutes County from 2018 to 2024?"
    raw_spec = {
        "partner_query_id": "service_deschutes_parser_noise",
        "task": "visualize_timeseries",
        "dataset": "openet",
        "location": "Deschutes County",
        "display_location": "Deschutes County",
        "location_type": "county",
        "variables": ["per_IRRIGATED", "CROP"],
        "start_date": "2018-01-01",
        "end_date": "2024-12-31",
        "interval": "yearly",
        "chart_type": "line",
    }

    initial, final = _run_confirmed_query(query, raw_spec)

    assert initial["spec"]["variables"] == ["per_IRRIGATED"]
    assert initial["spec"]["evidence_pattern"] == "trend_single"
    assert "compare_by" not in initial["spec"]
    assert final["summary"]["variable_labels"] == ["Irrigated Share (percent)"]
    _assert_partner_artifacts(final)


def test_irrigation_system_ranking_query_returns_ranked_primary_and_yearly_companion():
    query = "What irrigation systems were most often used for wheat fields in Jefferson County between 2015 and 2021?"

    initial = process_query(query, spec={"partner_query_id": "service_jefferson_itype"})

    assert initial["success"] is False
    assert initial["needs_confirmation"] is True
    assert initial["spec"]["variables"] == ["ITYPE"]
    assert initial["spec"]["crop_filter"] == "Wheat"
    assert initial["spec"]["evidence_pattern"] == "ranking_metric"
    assert initial["spec"]["compare_by"] == "ITYPE"
    assert "group_by" not in initial["spec"]
    assert "split_by" not in initial["spec"]

    final = confirm_query(
        pending_spec=initial["spec"],
        original_query=query,
    )

    assert final["success"] is True
    assert final["spec"]["evidence_pattern"] == "ranking_metric"
    assert final["summary"]["compare_by"] == "ITYPE"
    assert final["summary"]["group_count"] >= 2
    assert "trend" not in final["explanation"].lower()
    assert "most common category" in final["explanation"].lower()
    assert "Field Count" in final["data"].columns
    assert "Share (%)" in final["data"].columns
    assert len(final["secondary_views"]) == 1
    _assert_partner_artifacts(final)


def test_incomplete_query_returns_clarification_request():
    result = process_query(
        "Show temperature",
        spec={
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "variables": ["OBM"],
            "chart_type": "line",
        },
    )

    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert "location" in result["clarification_fields"]
    assert "time_range" in result["clarification_fields"]
    assert "Average Temperature (deg F)" in result["clarification_prompt"]


def test_clarification_reply_preserves_corvallis_display_case_until_confirmation():
    pending_spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "variables": ["PC"],
        "chart_type": "line",
        "interval": "daily",
        "clarification_needed": ["location", "time_range"],
    }

    first = process_clarification_reply(
        followup_query="Corvallis",
        pending_spec=pending_spec,
        original_query="show me precipitation",
    )
    assert first["needs_clarification"] is True
    assert first["spec"]["location"] == "corvallis"
    assert first["spec"]["display_location"] == "Corvallis"
    assert "location" in first["spec"]["confirmed_fields"]

    second = process_clarification_reply(
        followup_query="2024",
        pending_spec=first["spec"],
        original_query="show me precipitation",
    )
    assert second["needs_confirmation"] is True
    assert second["spec"]["location"] == "corvallis"
    assert second["spec"]["display_location"] == "Corvallis"
    assert second["spec"]["start_date"] == "2024-01-01"
    assert second["spec"]["end_date"] == "2024-12-31"


def test_location_only_followup_does_not_assume_time_range():
    result = process_clarification_reply(
        followup_query="Corvallis",
        pending_spec={
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "variables": ["OBM"],
            "chart_type": "line",
            "interval": "daily",
            "clarification_needed": ["location", "time_range"],
        },
        original_query="show me temperature",
    )

    assert result["needs_clarification"] is True
    assert result["spec"]["location"] == "corvallis"
    assert result["spec"]["display_location"] == "Corvallis"
    assert "start_date" not in result["spec"]
    assert "end_date" not in result["spec"]
    assert result["clarification_fields"] == ["time_range"]


def test_confirmation_edit_updates_crop_and_reconfirms():
    initial = process_query(
        "How has the amount of farmland planted with alfalfa changed in Morrow County between 2014 and 2022?",
        spec={"partner_query_id": "service_morrow_alfalfa_edit"},
    )

    result = apply_confirmation_edit(
        pending_spec=initial["spec"],
        original_query="How has the amount of farmland planted with alfalfa changed in Morrow County between 2014 and 2022?",
        field="crop",
        value="Winter Wheat",
    )

    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert result["spec"]["crop_filter"] == "Winter Wheat"
    assert result["spec"]["confirmation_status"] == "pending"
    assert "Crop filter: Winter Wheat" in result["confirmation_prompt"]


def test_confirmation_edit_updates_location_and_preserves_request():
    result = apply_confirmation_edit(
        pending_spec={
            "task": "visualize_timeseries",
            "dataset": "openet",
            "location": "Morrow County",
            "display_location": "Morrow County",
            "location_type": "county",
            "variables": ["ETa"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
            "chart_type": "line",
            "confirmation_status": "pending",
            "confirmed_fields": ["location", "time_range"],
        },
        original_query="Show ETa in Morrow County for 2024",
        field="location",
        value="Deschutes County",
    )

    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert result["spec"]["location"] == "Deschutes County"
    assert result["spec"]["display_location"] == "Deschutes County"
    assert result["spec"]["variables"] == ["ETa"]
    assert result["spec"]["confirmation_status"] == "pending"
    assert "Location: Deschutes County" in result["confirmation_prompt"]


def test_confirmation_edit_replaces_time_range_exactly():
    result = apply_confirmation_edit(
        pending_spec={
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "location": "corvallis",
            "display_location": "Corvallis",
            "location_type": "city",
            "variables": ["OBM"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "daily",
            "chart_type": "line",
            "confirmation_status": "pending",
            "confirmed_fields": ["location", "time_range"],
        },
        original_query="Show temperature in Corvallis for 2024",
        field="time_range",
        value={"start_date": "2023-03-01", "end_date": "2023-10-31"},
    )

    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert result["spec"]["start_date"] == "2023-03-01"
    assert result["spec"]["end_date"] == "2023-10-31"
    assert "Time range: 2023-03-01 to 2023-10-31" in result["confirmation_prompt"]


def test_confirmation_edit_updates_metric_and_rebuilds_dataset_routing():
    result = apply_confirmation_edit(
        pending_spec={
            "task": "visualize_timeseries",
            "dataset": "openet",
            "location": "corvallis",
            "display_location": "Corvallis",
            "location_type": "city",
            "variables": ["ETa"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
            "chart_type": "line",
            "compare_by": "ITYPE",
            "secondary_variables": ["ETa"],
            "confirmation_status": "pending",
        },
        original_query="Show ETa in Corvallis for 2024",
        field="metric",
        value="Average Temperature",
    )

    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert result["spec"]["variables"] == ["OBM"]
    assert result["spec"]["dataset"] == "agrimet"
    assert "compare_by" not in result["spec"]
    assert "secondary_variables" not in result["spec"]


def test_invalid_confirmation_edit_returns_clarification():
    result = apply_confirmation_edit(
        pending_spec={
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "location": "corvallis",
            "display_location": "Corvallis",
            "location_type": "city",
            "variables": ["OBM"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "daily",
            "chart_type": "line",
            "confirmation_status": "pending",
            "confirmed_fields": ["location", "time_range"],
        },
        original_query="Show temperature in Corvallis for 2024",
        field="time_range",
        value={"start_date": "2024-12-31", "end_date": "2024-01-01"},
    )

    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert result["clarification_fields"] == ["time_range"]


def test_visualization_explanation_mentions_trend_when_time_series_supports_it(monkeypatch):
    def fake_fetch_data(spec):
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "OBM": 40.0},
                    {"datetime": "2024-01-02", "OBM": 42.0},
                    {"datetime": "2024-01-03", "OBM": 44.0},
                    {"datetime": "2024-01-04", "OBM": 46.0},
                    {"datetime": "2024-01-05", "OBM": 48.0},
                    {"datetime": "2024-01-06", "OBM": 50.0},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    _, final = _run_confirmed_query(
        "Show temperature in Corvallis for early 2024",
        {
            "partner_query_id": "service_visualization_trend",
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "location": "Corvallis",
            "location_type": "city",
            "variables": ["OBM"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-06",
            "interval": "daily",
            "chart_type": "line",
        },
    )

    assert "increasing" in final["explanation"].lower()


def test_multivariable_comparison_adds_companion_view_after_confirmation(monkeypatch):
    def fake_fetch_data(spec):
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "AW": 1.0, "ETa": 0.8},
                    {"datetime": "2024-02-01", "AW": 1.2, "ETa": 1.0},
                    {"datetime": "2024-03-01", "AW": 1.1, "ETa": 0.9},
                    {"datetime": "2024-04-01", "AW": 1.4, "ETa": 1.2},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    _, final = _run_confirmed_query(
        "Compare AW and ETa in Douglas County for 2024",
        {
            "partner_query_id": "service_comparison_multivariate",
            "task": "visualize_timeseries",
            "dataset": "openet",
            "location": "Douglas County",
            "location_type": "county",
            "variables": ["AW", "ETa"],
            "start_date": "2024-01-01",
            "end_date": "2024-04-01",
            "interval": "monthly",
            "chart_type": "line",
            "evidence_pattern": "comparison_multivariate",
            "chart_package": "comparison_series",
            "source_datasets": ["openet"],
        },
    )

    assert final["spec"]["evidence_pattern"] == "comparison_multivariate"
    assert len(final["secondary_views"]) == 1
    assert "companion chart" in final["secondary_views"][0]["caption"].lower()


def test_grouped_comparison_defaults_time_range_and_runs_after_confirmation(monkeypatch):
    def fake_fetch_grouped_data(spec):
        assert spec["compare_by"] == "IRR_STATUS"
        assert spec["start_date"] == "2024-01-01"
        assert spec["end_date"] == "2024-12-31"
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "group": "Irrigated", "variable": "ETa", "value": 1.2},
                    {"datetime": "2024-01-01", "group": "Non-irrigated", "variable": "ETa", "value": 0.9},
                    {"datetime": "2024-02-01", "group": "Irrigated", "variable": "ETa", "value": 1.4},
                    {"datetime": "2024-02-01", "group": "Non-irrigated", "variable": "ETa", "value": 1.0},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_grouped_data", fake_fetch_grouped_data)

    initial = process_query(
        "Compare ETa for irrigated vs non-irrigated lentil fields in Grant County.",
        spec={
            "partner_query_id": "service_grouped_comparison",
            "task": "visualize_timeseries",
            "dataset": "openet",
            "location": "Grant County",
            "location_type": "county",
            "variables": ["ETa", "IRR_STATUS"],
        },
    )

    assert initial["needs_confirmation"] is True
    assert initial["spec"]["evidence_pattern"] == "comparison_grouped"
    assert initial["spec"]["start_date"] == "2024-01-01"
    assert initial["spec"]["end_date"] == "2024-12-31"

    final = confirm_query(
        pending_spec=initial["spec"],
        original_query="Compare ETa for irrigated vs non-irrigated lentil fields in Grant County.",
    )

    assert final["success"] is True
    assert final["summary"]["compare_by"] == "IRR_STATUS"
    assert len(final["secondary_views"]) == 1
    _assert_partner_artifacts(final)


def test_cross_dataset_comparison_returns_coordinated_views_after_confirmation(monkeypatch):
    def fake_fetch_data(spec):
        if spec["dataset"] == "openet":
            return {
                "spec": spec,
                "data": {
                    "records": [
                        {"datetime": "2024-01-01", "ETa": 0.8, "PPT": 0.3},
                        {"datetime": "2024-02-01", "ETa": 1.1, "PPT": 0.4},
                    ]
                },
            }
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "PEN_ET": 0.9},
                    {"datetime": "2024-02-01", "PEN_ET": 1.0},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    _, final = _run_confirmed_query(
        "Compare ETa, PEN_ET, and PPT in Corvallis for early 2024",
        {
            "partner_query_id": "service_cross_dataset",
            "task": "visualize_timeseries",
            "dataset": "openet",
            "location": "Corvallis",
            "location_type": "city",
            "variables": ["ETa", "PEN_ET", "PPT"],
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "interval": "monthly",
            "chart_type": "line",
            "evidence_pattern": "cross_dataset_comparison",
            "chart_package": ["primary_trend", "dataset_companion"],
            "source_datasets": ["openet", "agrimet"],
        },
    )

    assert final["success"] is True
    assert final["summary"]["source_datasets"] == ["openet", "agrimet"]
    assert len(final["secondary_views"]) == 1
    assert "agrimet" in final["secondary_views"][0]["caption"].lower()
    _assert_partner_artifacts(final)
