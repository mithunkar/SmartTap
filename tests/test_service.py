import pandas as pd

from smarttap_service import process_clarification_reply, process_query


def test_visualize_timeseries_with_mocked_spec():
    spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "corvallis",
        "variables": ["OBM"],
        "start_date": "2020-01-01",
        "end_date": "2020-01-03",
        "interval": "daily",
        "chart_type": "line",
    }
    result = process_query("Show temperature in Corvallis for early 2020", spec=spec)
    assert result["success"] is True
    assert result["summary"]["dataset"] == "agrimet"
    assert result["explanation"]


def test_statistical_summary_with_mocked_spec():
    spec = {
        "task": "statistical_summary",
        "dataset": "agrimet",
        "location": "corvallis",
        "variables": ["OBM"],
        "start_date": "2020-01-01",
        "end_date": "2020-01-10",
        "interval": "daily",
    }
    result = process_query("What is the average temperature in Corvallis?", spec=spec)
    assert result["success"] is True
    assert "mean" in result["summary"]
    assert "increasing" not in result["explanation"].lower()
    assert "decreasing" not in result["explanation"].lower()


def test_crop_summary_with_mocked_spec():
    spec = {
        "task": "summarize_crops",
        "location": "Corvallis",
        "location_type": "city",
        "year": 2024,
    }
    result = process_query("What crops are grown in Corvallis?", spec=spec)
    assert result["success"] is True
    assert result["summary"]["task"] == "summarize_crops"
    assert result["explanation"]


def test_incomplete_query_returns_clarification_request():
    spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "variables": ["OBM"],
        "chart_type": "line",
    }
    result = process_query("Show temperature", spec=spec)
    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert "location" in result["clarification_fields"]
    assert "time_range" in result["clarification_fields"]
    assert "variables=Avg Temp (°F)" in result["clarification_prompt"]


def test_agrimet_unknown_city_requests_supported_station():
    spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "Medford",
        "variables": ["OBM"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "chart_type": "line",
    }
    result = process_query("Show temperature in Medford for 2024", spec=spec)
    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert "station" in result["clarification_fields"]
    assert "local AgriMet dataset only supports" in result["clarification_prompt"]


def test_clarification_reply_patches_pending_spec():
    pending_spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "variables": ["PC"],
        "chart_type": "line",
        "interval": "daily",
        "clarification_needed": ["location", "time_range"],
    }
    result = process_clarification_reply(
        followup_query="Corvallis in 2024",
        pending_spec=pending_spec,
        original_query="show me precipitation",
    )
    assert result["success"] is True
    assert result["spec"]["location"].lower() == "corvallis"
    assert result["spec"]["start_date"] == "2024-01-01"
    assert result["spec"]["end_date"] == "2024-12-31"


def test_sequential_clarification_keeps_confirmed_location():
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
    assert first["spec"]["location"] == "Corvallis"
    assert "location" in first["spec"]["confirmed_fields"]

    second = process_clarification_reply(
        followup_query="2024",
        pending_spec=first["spec"],
        original_query="show me precipitation",
    )
    assert second["success"] is True
    assert second["spec"]["location"] == "Corvallis"
    assert second["spec"]["start_date"] == "2024-01-01"
    assert second["spec"]["end_date"] == "2024-12-31"


def test_location_only_followup_does_not_assume_time_range():
    pending_spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "variables": ["OBM"],
        "chart_type": "line",
        "interval": "daily",
        "clarification_needed": ["location", "time_range"],
    }
    result = process_clarification_reply(
        followup_query="Corvallis",
        pending_spec=pending_spec,
        original_query="show me temperature",
    )
    assert result["needs_clarification"] is True
    assert result["spec"]["location"] == "Corvallis"
    assert "start_date" not in result["spec"]
    assert "end_date" not in result["spec"]
    assert result["clarification_fields"] == ["time_range"]


def test_statistical_summary_regression_avoids_trend_language(monkeypatch):
    def fake_fetch_data(spec):
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "ETa": 0.16},
                    {"datetime": "2024-02-01", "ETa": 1.25},
                    {"datetime": "2024-03-01", "ETa": 2.41},
                    {"datetime": "2024-04-01", "ETa": 3.18},
                    {"datetime": "2024-05-01", "ETa": 3.72},
                    {"datetime": "2024-06-01", "ETa": 4.21},
                    {"datetime": "2024-07-01", "ETa": 5.33},
                    {"datetime": "2024-08-01", "ETa": 6.16},
                    {"datetime": "2024-09-01", "ETa": 2.91},
                    {"datetime": "2024-10-01", "ETa": 1.37},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    spec = {
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
    }

    result = process_query("What is the average ETa in Hood River in 2024?", spec=spec)

    assert result["success"] is True
    explanation = result["explanation"].lower()
    assert "trend" not in explanation
    assert "increasing" not in explanation
    assert "decreasing" not in explanation
    assert "average" in explanation
    assert "median" in explanation


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

    spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "Corvallis",
        "location_type": "city",
        "variables": ["OBM"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-06",
        "interval": "daily",
        "chart_type": "line",
    }

    result = process_query("Show temperature in Corvallis for early 2024", spec=spec)

    assert result["success"] is True
    assert "increasing" in result["explanation"].lower()


def test_crop_summary_explanation_mentions_top_category(monkeypatch):
    class FakeLocationQuery:
        def query_crops_by_city(self, clean_location, year):
            del clean_location, year
            return pd.DataFrame(
                {
                    "crop_name": ["Alfalfa", "Alfalfa", "Corn"],
                    "crop_group": ["Hay", "Hay", "Grain"],
                    "OPENET_ID": [1, 2, 3],
                }
            )

    monkeypatch.setattr("smarttap_service._init_location_query", lambda: FakeLocationQuery())

    spec = {
        "task": "summarize_crops",
        "location": "Corvallis",
        "location_type": "city",
        "year": 2024,
    }

    result = process_query("What crops are grown in Corvallis?", spec=spec)

    assert result["success"] is True
    explanation = result["explanation"].lower()
    assert "alfalfa" in explanation
    assert "fields" in explanation
