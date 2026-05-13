from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from smarttap_api import app


client = TestClient(app)


def test_health_returns_metric_options():
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "smarttap-api"
    assert any(option["code"] == "OBM" for option in payload["metric_options"])


def test_query_endpoint_serializes_success(monkeypatch):
    def fake_process_query(query: str, spec=None):
        assert query == "Show temperature in Corvallis for July 2024"
        assert spec is None
        return {
            "success": True,
            "needs_clarification": False,
            "needs_confirmation": False,
            "error": None,
            "spec": {"task": "visualize_timeseries", "location": "Corvallis"},
            "summary": {"location": "Corvallis", "row_count": 2},
            "explanation": "Temperatures increased slightly during the period.",
            "data_preview": pd.DataFrame(
                [{"datetime": "2024-07-01", "OBM": 72.0}, {"datetime": "2024-07-02", "OBM": 74.0}]
            ),
                "data": pd.DataFrame(
                    [{"datetime": "2024-07-01", "OBM": 72.0}, {"datetime": "2024-07-02", "OBM": 74.0}]
                ),
                "chart_bytes": b"fake-png",
                "vega_spec": {
                    "mark": "line",
                    "data": {
                        "values": [
                            {"datetime": "2024-07-01", "OBM": 72.0},
                            {"datetime": "2024-07-02", "OBM": 74.0},
                        ]
                    },
                    "encoding": {
                        "x": {"field": "datetime", "type": "temporal"},
                        "y": {"field": "OBM", "type": "quantitative", "title": "Average Temperature (deg F)"},
                    },
                },
                "secondary_views": [
                    {
                        "caption": "Companion view",
                        "chart_bytes": b"secondary-png",
                        "data_preview": pd.DataFrame([{"label": "A", "value": 1}]),
                        "vega_spec": {
                            "mark": "bar",
                            "data": {"values": [{"label": "A", "value": 1}]},
                            "encoding": {
                                "x": {"field": "label", "type": "nominal"},
                                "y": {"field": "value", "type": "quantitative"},
                            },
                        },
                        "files": {"png": "outputs/example.png"},
                    }
                ],
            "files": {"png": "outputs/example.png"},
            "validation_report": {"status": "ok"},
            "clarification_prompt": None,
            "confirmation_prompt": None,
            "clarification_fields": [],
        }

    monkeypatch.setattr("smarttap_api.process_query", fake_process_query)

    response = client.post("/api/query", json={"query": "Show temperature in Corvallis for July 2024"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["chart_image_url"].startswith("data:image/png;base64,")
    assert payload["chart_model"]["kind"] == "line"
    assert payload["data_preview"]["columns"] == ["datetime", "OBM"]
    assert payload["secondary_views"][0]["caption"] == "Companion view"
    assert payload["secondary_views"][0]["chart_model"]["kind"] == "bar"
    assert payload["secondary_views"][0]["chart_image_url"].startswith("data:image/png;base64,")


def test_followup_endpoint_uses_followup_contract(monkeypatch):
    def fake_followup_reply(*, followup_query: str, pending_spec: dict, original_query: str):
        assert followup_query == "Use mint"
        assert pending_spec == {"location": "Corvallis"}
        assert original_query == "What crops are grown in Corvallis?"
        return {
            "success": False,
            "needs_clarification": False,
            "needs_confirmation": True,
            "error": None,
            "spec": {"crop_filter": "Mint"},
            "summary": {"status": "confirmation_needed"},
            "explanation": "",
            "data_preview": None,
            "data": None,
            "chart_bytes": None,
            "vega_spec": None,
            "secondary_views": [],
            "files": {},
            "validation_report": None,
            "clarification_prompt": None,
            "confirmation_prompt": "Please confirm the updated request.",
            "clarification_fields": [],
        }

    monkeypatch.setattr("smarttap_api.process_followup_reply", fake_followup_reply)

    response = client.post(
        "/api/followup",
        json={
            "followup_query": "Use mint",
            "pending_spec": {"location": "Corvallis"},
            "original_query": "What crops are grown in Corvallis?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["needs_confirmation"] is True
    assert payload["confirmation_prompt"] == "Please confirm the updated request."


def test_confirmation_edit_endpoint_serializes_clarification(monkeypatch):
    def fake_apply_confirmation_edit(*, pending_spec: dict, original_query: str, field: str, value):
        assert field == "time_range"
        assert pending_spec == {"location": "Corvallis"}
        assert original_query == "Show ETa in Corvallis"
        assert value == {"start_date": "2024-01-01", "end_date": "2024-12-31"}
        return {
            "success": False,
            "needs_clarification": True,
            "needs_confirmation": False,
            "error": None,
            "spec": {"location": "Corvallis"},
            "summary": {"status": "clarification_needed"},
            "explanation": "",
            "data_preview": None,
            "data": None,
            "chart_bytes": None,
            "vega_spec": None,
            "secondary_views": [],
            "files": {},
            "validation_report": None,
            "clarification_prompt": "I need a narrower time range.",
            "confirmation_prompt": None,
            "clarification_fields": ["time_range"],
        }

    monkeypatch.setattr("smarttap_api.apply_confirmation_edit", fake_apply_confirmation_edit)

    response = client.post(
        "/api/confirmation/edit",
        json={
            "pending_spec": {"location": "Corvallis"},
            "original_query": "Show ETa in Corvallis",
            "field": "time_range",
            "value": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["needs_clarification"] is True
    assert payload["clarification_fields"] == ["time_range"]


def test_confirmation_confirm_endpoint_serializes_result(monkeypatch):
    def fake_confirm_query(*, pending_spec: dict, original_query: str):
        assert pending_spec == {"location": "Corvallis"}
        assert original_query == "Show ETa in Corvallis"
        return {
            "success": True,
            "needs_clarification": False,
            "needs_confirmation": False,
            "error": None,
            "spec": {"location": "Corvallis"},
            "summary": {"location": "Corvallis"},
            "explanation": "ETa was stable.",
            "data_preview": pd.DataFrame([{"datetime": "2024-01-01", "ETa": 1.2}]),
            "data": pd.DataFrame([{"datetime": "2024-01-01", "ETa": 1.2}]),
            "chart_bytes": b"final-png",
            "vega_spec": {
                "mark": "line",
                "data": {"values": [{"datetime": "2024-01-01", "ETa": 1.2}]},
                "encoding": {
                    "x": {"field": "datetime", "type": "temporal"},
                    "y": {"field": "ETa", "type": "quantitative", "title": "ETa"},
                },
            },
            "secondary_views": [],
            "files": {"png": "outputs/final.png"},
            "validation_report": {"status": "ok"},
            "clarification_prompt": None,
            "confirmation_prompt": None,
            "clarification_fields": [],
        }

    monkeypatch.setattr("smarttap_api.confirm_query", fake_confirm_query)

    response = client.post(
        "/api/confirmation/confirm",
        json={
            "pending_spec": {"location": "Corvallis"},
            "original_query": "Show ETa in Corvallis",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["explanation"] == "ETa was stable."
