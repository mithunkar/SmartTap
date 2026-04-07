from smarttap_service import process_query


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
