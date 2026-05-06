from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from smarttap_service import confirm_query, process_query


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "acceptance_queries.json"


def _load_cases() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text())
    return payload.get("cases", [])


@pytest.fixture(autouse=True)
def _isolated_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _mock_time_series_records(spec: dict) -> list[dict]:
    interval = str(spec.get("interval") or "monthly")
    start_date = spec.get("start_date") or f"{spec.get('year', 2024)}-01-01"
    freq = {"daily": "D", "monthly": "MS", "yearly": "YS"}.get(interval, "MS")
    dates = pd.date_range(start=start_date, periods=3, freq=freq)

    records: list[dict] = []
    for index, dt in enumerate(dates, start=1):
        row = {"datetime": dt.strftime("%Y-%m-%d")}
        for offset, variable in enumerate(spec.get("variables") or []):
            if variable == "IRR_STATUS":
                row[variable] = 1 if index % 2 else 0
            elif variable == "ITYPE":
                row[variable] = index + offset
            elif variable == "per_IRRIGATED":
                row[variable] = 35 + (index * 5)
            elif variable in {"AVG_HUM"}:
                row[variable] = 45 + (index * 3)
            elif variable in {"AVG_TMP", "OBM"}:
                row[variable] = 50 + (index * 2)
            elif variable == "Kc":
                row[variable] = round(0.55 + (index * 0.08), 3)
            else:
                row[variable] = round((index * 1.25) + offset, 3)
        records.append(row)
    return records


def _assert_expected_fields(result_spec: dict, expected: dict) -> None:
    for key, value in expected.items():
        if key == "status":
            continue
        if key == "clarification_fields":
            assert result_spec.get("clarification_needed") == value
            continue
        assert result_spec.get(key) == value


def test_acceptance_cases_resolve_initial_state():
    for case in _load_cases():
        result = process_query(case["prompt"], spec=dict(case["raw_spec"]))
        expected = case["expected_initial"]

        if expected["status"] == "confirmation":
            assert result["success"] is False, case["id"]
            assert result["needs_confirmation"] is True, case["id"]
            assert result["needs_clarification"] is False, case["id"]
            _assert_expected_fields(result["spec"], expected)
            continue

        if expected["status"] == "clarification":
            assert result["success"] is False, case["id"]
            assert result["needs_clarification"] is True, case["id"]
            assert result["needs_confirmation"] is False, case["id"]
            assert result["clarification_fields"] == expected["clarification_fields"], case["id"]
            _assert_expected_fields(result["spec"], expected)
            continue

        raise AssertionError(f"Unknown expected initial status for {case['id']}: {expected['status']}")


def test_acceptance_confirmation_cases_generate_partner_artifacts(monkeypatch):
    cases = _load_cases()
    no_data_cases = {
        "workbook_row_10": "No OpenET fields matched crop 'Soybean' in Wasco County for 2015-01-01 to 2021-12-31.",
        "workbook_row_18": "No usable AgriMet values were available for Average Humidity (percent) at Imbler, Oregon AgriMet Weather Station (imbo) for 2016-01-01 to 2022-12-31.",
        "workbook_row_20": "No usable AgriMet values were available for Crop Coefficient at Sublimity, Oregon Weather Station (subo) for 2019-01-01 to 2023-12-31.",
    }

    def fake_fetch_data(spec):
        partner_query_id = str(spec.get("partner_query_id") or "")
        if partner_query_id in no_data_cases:
            return {
                "spec": {**spec, "no_data_reason": no_data_cases[partner_query_id]},
                "data": {"records": []},
            }
        return {"spec": spec, "data": {"records": _mock_time_series_records(spec)}}

    class FakeLocationQuery:
        def query_crops_by_city(self, clean_location, year):
            del clean_location, year
            return pd.DataFrame(
                {
                    "crop_name": ["Corn", "Corn", "Hazelnut", "Mint"],
                    "crop_group": ["Grain", "Grain", "Orchard", "Herb"],
                    "OPENET_ID": [1, 2, 3, 4],
                }
            )

        def query_categorical_counts_by_location(
            self,
            *,
            location,
            location_type,
            compare_by,
            start_date,
            end_date,
            crop_filter=None,
            max_distance=1,
        ):
            del location, location_type, compare_by, start_date, end_date, crop_filter, max_distance
            return pd.DataFrame(
                {
                    "datetime": pd.to_datetime(
                        [
                            "2015-01-01",
                            "2015-01-01",
                            "2016-01-01",
                            "2016-01-01",
                        ]
                    ),
                    "group": ["ITYPE 1", "ITYPE 2", "ITYPE 1", "ITYPE 2"],
                    "field_count": [10, 6, 12, 5],
                    "compare_by": ["ITYPE", "ITYPE", "ITYPE", "ITYPE"],
                    "location": ["Jefferson County"] * 4,
                    "location_type": ["county"] * 4,
                }
            )

        def query_crops_by_county(self, clean_location, year):
            del clean_location, year
            return pd.DataFrame(
                {
                    "crop_name": ["Corn", "Corn", "Hazelnut", "Mint"],
                    "crop_group": ["Grain", "Grain", "Orchard", "Herb"],
                    "OPENET_ID": [1, 2, 3, 4],
                }
            )

    monkeypatch.setattr("smarttap_service.fetch_data", fake_fetch_data)
    monkeypatch.setattr("smarttap_service._init_location_query", lambda: FakeLocationQuery())

    for case in cases:
        if case["expected_initial"]["status"] != "confirmation":
            continue

        initial = process_query(case["prompt"], spec=dict(case["raw_spec"]))
        assert initial["needs_confirmation"] is True, case["id"]

        final = confirm_query(
            pending_spec=initial["spec"],
            original_query=case["prompt"],
        )

        assert final["success"] is True, case["id"]
        assert final["summary"]["dataset"] == case["expected_final"]["dataset"], case["id"]
        assert final["spec"]["evidence_pattern"] == case["expected_final"]["evidence_pattern"], case["id"]
        assert final["summary"]["status"] == case["expected_final"]["status"], case["id"]
        assert final["summary"]["source_datasets"] == case["expected_initial"]["source_datasets"], case["id"]
        assert final["summary"]["variable_labels"], case["id"]

        results_dir = Path(final["files"]["results_dir"])
        assert results_dir.parts[:2] == ("outputs", "partner_queries"), case["id"]
        assert results_dir.name == case["id"], case["id"]
        for filename in ["prompt.txt", "resolved_query.json", "chart.png", "data.csv", "vega.json", "validation.json", "verification.md"]:
            assert (results_dir / filename).exists(), f"{case['id']} missing {filename}"
