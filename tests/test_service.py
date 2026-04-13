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
    assert result["spec"]["evidence_pattern"] == "trend_single"


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
    assert len(result["secondary_views"]) == 1


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


def test_multivariable_comparison_adds_companion_view(monkeypatch):
    def fake_fetch_data(spec):
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "AW": 1.0, "ETa": 0.8},
                    {"datetime": "2024-02-01", "AW": 1.2, "ETa": 1.0},
                    {"datetime": "2024-03-01", "AW": 1.1, "ETa": 0.9},
                    {"datetime": "2024-04-01", "AW": 1.4, "ETa": 1.2},
                    {"datetime": "2024-05-01", "AW": 1.6, "ETa": 1.3},
                    {"datetime": "2024-06-01", "AW": 1.7, "ETa": 1.5},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    spec = {
        "task": "visualize_timeseries",
        "dataset": "openet",
        "location": "Douglas County",
        "location_type": "county",
        "variables": ["AW", "ETa"],
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "interval": "monthly",
        "chart_type": "line",
        "evidence_pattern": "comparison_multivariate",
        "chart_package": "comparison_series",
        "source_datasets": ["openet"],
    }

    result = process_query("Compare AW and ETa in Douglas County for 2024", spec=spec)

    assert result["success"] is True
    assert result["spec"]["evidence_pattern"] == "comparison_multivariate"
    assert len(result["secondary_views"]) == 1
    assert "companion chart" in result["secondary_views"][0]["caption"].lower()


def test_cross_dataset_comparison_returns_coordinated_views(monkeypatch):
    def fake_fetch_data(spec):
        if spec["dataset"] == "openet":
            return {
                "spec": spec,
                "data": {
                    "records": [
                        {"datetime": "2024-01-01", "ETa": 0.8, "PPT": 0.3},
                        {"datetime": "2024-02-01", "ETa": 1.1, "PPT": 0.4},
                        {"datetime": "2024-03-01", "ETa": 1.3, "PPT": 0.5},
                    ]
                },
            }
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "PEN_ET": 0.9},
                    {"datetime": "2024-02-01", "PEN_ET": 1.0},
                    {"datetime": "2024-03-01", "PEN_ET": 1.2},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    spec = {
        "task": "visualize_timeseries",
        "dataset": "openet",
        "location": "Corvallis",
        "location_type": "city",
        "variables": ["ETa", "PEN_ET", "PPT"],
        "start_date": "2024-01-01",
        "end_date": "2024-03-01",
        "interval": "monthly",
        "chart_type": "line",
        "evidence_pattern": "cross_dataset_comparison",
        "chart_package": ["primary_trend", "dataset_companion"],
        "source_datasets": ["openet", "agrimet"],
    }

    result = process_query("Compare ETa, PEN_ET, and PPT in Corvallis for early 2024", spec=spec)

    assert result["success"] is True
    assert result["spec"]["evidence_pattern"] == "cross_dataset_comparison"
    assert len(result["secondary_views"]) == 1
    assert "source_dataset" in result["data_preview"].columns
    assert "across openet, agrimet" in result["explanation"].lower()


def test_service_preserves_inferred_crop_filter_in_resolved_request(monkeypatch):
    def fake_fetch_data(spec):
        assert spec.get("crop_filter") == "Cucumber"
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "NIWR": 0.8, "AW": 0.7, "ETa": 0.6},
                    {"datetime": "2024-02-01", "NIWR": 1.0, "AW": 0.9, "ETa": 0.8},
                    {"datetime": "2024-03-01", "NIWR": 1.2, "AW": 1.0, "ETa": 0.9},
                    {"datetime": "2024-04-01", "NIWR": 1.3, "AW": 1.1, "ETa": 1.0},
                    {"datetime": "2024-05-01", "NIWR": 1.4, "AW": 1.2, "ETa": 1.1},
                    {"datetime": "2024-06-01", "NIWR": 1.5, "AW": 1.3, "ETa": 1.2},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    spec = {
        "task": "visualize_timeseries",
        "dataset": "openet",
        "location": "Corvallis",
        "location_type": "city",
        "variables": ["NIWR", "AW", "ETa"],
        "start_date": "2016-01-01",
        "end_date": "2024-12-31",
        "interval": "monthly",
        "chart_type": "line",
        "openet_geo": "location",
    }

    result = process_query(
        "For cucumber farms in Corvallis, how did plant water needs, irrigation demand, and water applied evolve from 2016 to 2024?",
        spec=spec,
    )

    assert result["success"] is True
    assert result["spec"]["crop_filter"] == "Cucumber"
    assert result["summary"]["crop_filter"] == "Cucumber"
    assert "cucumber" in result["explanation"].lower()


def test_service_preserves_pasture_crop_filter_and_hides_none(monkeypatch):
    def fake_fetch_data(spec):
        assert spec.get("crop_filter") == "Pasture"
        return {
            "spec": spec,
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "ETa": 0.6, "NIWR_VOLUME": 0.8, "AW": 0.7},
                    {"datetime": "2024-02-01", "ETa": 0.8, "NIWR_VOLUME": 1.0, "AW": 0.9},
                    {"datetime": "2024-03-01", "ETa": 0.9, "NIWR_VOLUME": 1.1, "AW": 1.0},
                    {"datetime": "2024-04-01", "ETa": 1.0, "NIWR_VOLUME": 1.2, "AW": 1.1},
                    {"datetime": "2024-05-01", "ETa": 1.1, "NIWR_VOLUME": 1.3, "AW": 1.2},
                    {"datetime": "2024-06-01", "ETa": 1.2, "NIWR_VOLUME": 1.4, "AW": 1.3},
                ]
            },
        }

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)

    spec = {
        "task": "visualize_timeseries",
        "dataset": "openet",
        "location": "Corvallis",
        "location_type": "city",
        "variables": ["ETa", "NIWR_VOLUME", "AW"],
        "start_date": "2016-01-01",
        "end_date": "2024-12-31",
        "interval": "monthly",
        "chart_type": "line",
        "openet_geo": "location",
    }

    result = process_query(
        "For pastures in Corvallis, how did plant water needs, irrigation demand, and water applied evolve from 2016 to 2024?",
        spec=spec,
    )

    assert result["success"] is True
    assert result["spec"]["crop_filter"] == "Pasture"
    assert result["summary"]["crop_filter"] == "Pasture"
    assert "none" not in str(result["summary"]).lower()
    assert "pasture" in result["explanation"].lower()


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
