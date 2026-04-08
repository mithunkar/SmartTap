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
