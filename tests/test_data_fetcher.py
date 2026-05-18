#!/usr/bin/env python3
"""
Unit tests for data_fetcher module
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_fetcher import fetch_data, fetch_agrimet_data, fetch_openet_data
from core.location_crop_query import LocationCropQuery
from core.location_resolver import resolve_agrimet_location
from core.validation import validate_payload


class TestDataFetcher(unittest.TestCase):
    """Test data fetching functionality"""

    @staticmethod
    def _fake_agrimet_api_frame(
        start: str = "2020-01-01",
        periods: int = 5,
    ) -> pd.DataFrame:
        dates = pd.date_range(start, periods=periods, freq="D")
        return pd.DataFrame(
            {
                "date": dates,
                "datetime": dates,
                "max_temp_f": [50.0 + index for index in range(periods)],
                "min_temp_f": [30.0 + index for index in range(periods)],
                "daily_precip_in": [0.1 * (index + 1) for index in range(periods)],
                "solar_langley": [10.0 + index for index in range(periods)],
                "wind_speed_mph": [4.0 + (index * 0.5) for index in range(periods)],
                "rh": [45.0 + index for index in range(periods)],
                "et": [1.0 + (index * 0.1) for index in range(periods)],
                "kc": [0.5 + (index * 0.01) for index in range(periods)],
            }
        )
    
    def test_agrimet_basic_fetch(self):
        """Test basic AgriMet data fetching"""
        spec = {
            "dataset": "agrimet",
            "location": "corvallis",
            "variables": ["OBM"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-10",
            "interval": "daily"
        }
        
        with patch("core.data_fetcher.fetch_agrimet_api_data", return_value=self._fake_agrimet_api_frame(periods=10)):
            payload = fetch_agrimet_data(spec)
        
        # Verify structure
        self.assertIn("spec", payload)
        self.assertIn("data", payload)
        self.assertIn("records", payload["data"])
        
        # Verify records exist
        records = payload["data"]["records"]
        self.assertGreater(len(records), 0, "Should have records")
        
        # Verify required fields
        first_record = records[0]
        self.assertIn("datetime", first_record)
        self.assertIn("OBM", first_record)
    
    def test_agrimet_missing_location(self):
        """Invalid locations should return a clear API no-data payload."""
        spec = {
            "dataset": "agrimet",
            "location": "invalid_location",
            "variables": ["OBM"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-10"
        }

        with patch("core.data_fetcher.fetch_agrimet_api_data", side_effect=ValueError("Station not found for 'invalid_location'.")):
            payload = fetch_agrimet_data(spec)

        self.assertEqual(payload["data"]["records"], [])
        self.assertEqual(payload["spec"]["source_mode"], "agrimet_api")
        self.assertIn("No AgriMet API data was available", payload["spec"]["no_data_reason"])
    
    def test_agrimet_multiple_variables(self):
        """Test fetching multiple variables"""
        spec = {
            "dataset": "agrimet",
            "location": "corvallis",
            "variables": ["OBM", "PC", "SR"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05",
            "interval": "daily"
        }
        
        with patch("core.data_fetcher.fetch_agrimet_api_data", return_value=self._fake_agrimet_api_frame(periods=5)):
            payload = fetch_agrimet_data(spec)
        records = payload["data"]["records"]
        
        # Verify all variables present
        first_record = records[0]
        self.assertIn("OBM", first_record)
        self.assertIn("PC", first_record)
        self.assertIn("SR", first_record)

    def test_agrimet_county_resolves_to_api_station(self):
        """County mentions should resolve through station metadata and use the API runtime path."""
        match = resolve_agrimet_location("Benton County", local_only=True)
        self.assertIsNotNone(match)
        self.assertEqual(match["canonical_location"], "corvallis")

        spec = {
            "dataset": "agrimet",
            "location": "Benton County",
            "variables": ["OBM"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-03",
            "interval": "daily",
        }

        with patch("core.data_fetcher.fetch_agrimet_api_data", return_value=self._fake_agrimet_api_frame(periods=3)):
            payload = fetch_agrimet_data(spec)
        self.assertEqual(payload["spec"]["location"], "corvallis")
        self.assertEqual(payload["spec"]["resolved_station_id"], "crvo")
        self.assertEqual(payload["spec"]["source_mode"], "agrimet_api")
        self.assertEqual(payload["spec"]["fetch_mode"], "api")
        self.assertEqual(payload["spec"]["station_id"], "crvo")
        self.assertEqual(len(payload["data"]["records"]), 3)
    
    def test_openet_legacy_huc_runtime_route_is_disabled(self):
        spec = {
            "dataset": "openet",
            "openet_geo": "huc8",
            "huc8_code": "18010204",
            "variables": ["ETa"],
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
            "interval": "monthly"
        }

        with self.assertRaises(ValueError):
            fetch_openet_data(spec)
    
    def test_router_agrimet(self):
        """Test main fetch_data router for AgriMet"""
        spec = {
            "dataset": "agrimet",
            "location": "corvallis",
            "variables": ["OBM"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05"
        }
        
        with patch("core.data_fetcher.fetch_agrimet_api_data", return_value=self._fake_agrimet_api_frame(periods=5)):
            payload = fetch_data(spec)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["spec"]["dataset"], "agrimet")
    
    def test_date_filtering(self):
        """Test that date filtering works correctly"""
        spec = {
            "dataset": "agrimet",
            "location": "corvallis",
            "variables": ["OBM"],
            "start_date": "2020-07-01",
            "end_date": "2020-07-03",
            "interval": "daily"
        }
        
        with patch("core.data_fetcher.fetch_agrimet_api_data", return_value=self._fake_agrimet_api_frame(start="2020-07-01", periods=3)):
            payload = fetch_agrimet_data(spec)
        records = payload["data"]["records"]
        
        # Should have 3 days of data
        self.assertEqual(len(records), 3, f"Expected 3 records, got {len(records)}")

    def test_openet_crop_filter_empty_result_has_specific_error_message(self):
        """Crop-filtered empty results should surface a no-data payload instead of raising."""

        class FakeLocationCropQuery:
            def __init__(self, *args, **kwargs):
                pass

            def query_variable_by_city(self, **kwargs):
                return __import__("pandas").DataFrame(), {"no_data_reason": "no_variable_rows"}

        spec = {
            "dataset": "openet",
            "openet_geo": "location",
            "location": "Corvallis",
            "location_type": "city",
            "crop_filter": "Cucumber",
            "variables": ["ETa"],
            "start_date": "2016-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
        }

        with patch("core.data_fetcher.LocationCropQuery", FakeLocationCropQuery):
            payload = fetch_openet_data(spec)

        self.assertEqual(payload["data"]["records"], [])
        self.assertEqual(
            payload["spec"]["no_data_reason"],
            "No OpenET variable rows were found for Cucumber fields near Corvallis for 2016-01-01 to 2024-12-31.",
        )

    def test_openet_crop_filter_no_matching_fields_has_specific_error_message(self):
        """Crop-filtered empty field matches should point to the crop/location filter failure."""

        class FakeLocationCropQuery:
            def __init__(self, *args, **kwargs):
                pass

            def query_variable_by_city(self, **kwargs):
                return __import__("pandas").DataFrame(), {"no_data_reason": "no_crop_fields"}

        spec = {
            "dataset": "openet",
            "openet_geo": "location",
            "location": "Corvallis",
            "location_type": "city",
            "crop_filter": "Cucumber",
            "variables": ["ETa"],
            "start_date": "2016-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
        }

        with patch("core.data_fetcher.LocationCropQuery", FakeLocationCropQuery):
            payload = fetch_openet_data(spec)

        self.assertEqual(payload["data"]["records"], [])
        self.assertEqual(
            payload["spec"]["no_data_reason"],
            "No OpenET fields matched crop 'Cucumber' near Corvallis for 2016-01-01 to 2024-12-31.",
        )

    def test_openet_volume_variables_default_to_sum_aggregation(self):
        seen_aggregation = {}

        class FakeLocationCropQuery:
            def __init__(self, *args, **kwargs):
                pass

            def query_variable_by_county(self, **kwargs):
                seen_aggregation["value"] = kwargs["aggregation"]
                return pd.DataFrame({"datetime": pd.to_datetime(["2024-01-01"]), "AW": [1.25]}), {}

        spec = {
            "dataset": "openet",
            "openet_geo": "location",
            "location": "Umatilla County",
            "location_type": "county",
            "variables": ["AW"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
        }

        with patch("core.data_fetcher.LocationCropQuery", FakeLocationCropQuery):
            payload = fetch_openet_data(spec)

        self.assertEqual(seen_aggregation["value"], "sum")
        self.assertEqual(payload["data"]["records"][0]["AW"], 1.25)

    def test_openet_rate_variables_default_to_mean_aggregation(self):
        seen_aggregation = {}

        class FakeLocationCropQuery:
            def __init__(self, *args, **kwargs):
                pass

            def query_variable_by_county(self, **kwargs):
                seen_aggregation["value"] = kwargs["aggregation"]
                return pd.DataFrame({"datetime": pd.to_datetime(["2024-01-01"]), "ETa": [0.75]}), {}

        spec = {
            "dataset": "openet",
            "openet_geo": "location",
            "location": "Umatilla County",
            "location_type": "county",
            "variables": ["ETa"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "interval": "monthly",
        }

        with patch("core.data_fetcher.LocationCropQuery", FakeLocationCropQuery):
            payload = fetch_openet_data(spec)

        self.assertEqual(seen_aggregation["value"], "mean")
        self.assertEqual(payload["data"]["records"][0]["ETa"], 0.75)

    def test_agrimet_pen_et_uses_api_fallback_even_for_local_station(self):
        spec = {
            "dataset": "agrimet",
            "location": "pendleton",
            "display_location": "Pendleton",
            "variables": ["PEN_ET"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
        }

        fake_api = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "datetime": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "et": [1.1, 1.2, 1.3],
                "max_temp_f": [50.0, 51.0, 52.0],
                "min_temp_f": [32.0, 33.0, 34.0],
                "daily_precip_in": [0.0, 0.0, 0.0],
                "solar_langley": [10.0, 11.0, 12.0],
                "wind_speed_mph": [4.0, 4.5, 5.0],
            }
        )

        with patch("core.data_fetcher.fetch_agrimet_api_data", return_value=fake_api) as mocked_api:
            payload = fetch_agrimet_data(spec)

        mocked_api.assert_called_once()
        self.assertEqual(payload["spec"]["fetch_mode"], "api")
        self.assertEqual(payload["spec"]["source_mode"], "agrimet_api")
        self.assertEqual(payload["spec"]["station_id"], "echo")
        self.assertEqual(payload["data"]["records"][0]["PEN_ET"], 1.1)

    def test_agrimet_api_failure_returns_no_data_payload(self):
        spec = {
            "dataset": "agrimet",
            "location": "la grande",
            "display_location": "La Grande",
            "variables": ["AVG_HUM"],
            "start_date": "2016-01-01",
            "end_date": "2022-12-31",
        }

        with patch("core.data_fetcher.fetch_agrimet_api_data", side_effect=ValueError("Station not found for 'imbo'.")):
            payload = fetch_agrimet_data(spec)

        self.assertEqual(payload["data"]["records"], [])
        self.assertIn("No AgriMet API data was available for Average Humidity (percent)", payload["spec"]["no_data_reason"])
        self.assertIn("API detail: Station not found for 'imbo'.", payload["spec"]["no_data_reason"])

    def test_agrimet_api_fallback_tries_next_valid_candidate(self):
        spec = {
            "dataset": "agrimet",
            "location": "Salem",
            "variables": ["Kc"],
            "start_date": "2019-01-01",
            "end_date": "2023-12-31",
        }

        fake_api = pd.DataFrame(
            {
                "date": pd.to_datetime(["2019-01-01", "2019-01-02"]),
                "kc": [0.62, 0.63],
            }
        )
        candidates = [
            {
                "canonical_location": "salem",
                "display_location": "Salem",
                "station_id": "subo",
                "station_title": "Sublimity, Oregon Weather Station",
                "station_install_date": "2024-02-22",
                "valid_for_requested_range": True,
                "supported_local": False,
            },
            {
                "canonical_location": "corvallis",
                "display_location": "Salem",
                "station_id": "crvo",
                "station_title": "Corvallis, Oregon Agrimet Weather Station",
                "station_install_date": "1990-02-27",
                "valid_for_requested_range": True,
                "supported_local": True,
            },
        ]

        with patch("core.data_fetcher.resolve_agrimet_candidates", return_value=candidates):
            with patch(
                "core.data_fetcher.fetch_agrimet_api_data",
                side_effect=[ValueError("Station not found for 'subo'."), fake_api],
            ) as mocked_api:
                payload = fetch_agrimet_data(spec)

        self.assertEqual(mocked_api.call_count, 2)
        self.assertEqual(payload["spec"]["station_id"], "crvo")
        self.assertEqual(payload["spec"]["data_station_id"], "crvo")
        self.assertEqual(payload["spec"]["api_station_candidates_tried"], ["subo", "crvo"])
        self.assertIn("using crvo instead", " ".join(payload["spec"].get("notes") or []).lower())
        self.assertEqual(payload["data"]["records"][0]["Kc"], 0.62)

    def test_agrimet_invalid_station_range_returns_clear_no_data(self):
        spec = {
            "dataset": "agrimet",
            "location": "Salem",
            "variables": ["Kc"],
            "start_date": "2019-01-01",
            "end_date": "2023-12-31",
        }
        candidates = [
            {
                "canonical_location": "salem",
                "display_location": "Salem",
                "station_id": "subo",
                "station_title": "Sublimity, Oregon Weather Station",
                "station_install_date": "2024-02-22",
                "valid_for_requested_range": False,
                "supported_local": False,
            }
        ]

        with patch("core.data_fetcher.resolve_agrimet_candidates", return_value=candidates):
            payload = fetch_agrimet_data(spec)

        self.assertEqual(payload["data"]["records"], [])
        self.assertIn("No AgriMet station active near Salem could serve Crop Coefficient", payload["spec"]["no_data_reason"])
        self.assertIn("installed 2024-02-22", payload["spec"]["no_data_reason"])

    def test_validate_payload_marks_all_null_requested_variables_unusable(self):
        payload = {
            "spec": {"variables": ["AVG_HUM"], "display_location": "La Grande"},
            "data": {
                "records": [
                    {"datetime": "2024-01-01", "AVG_HUM": None},
                    {"datetime": "2024-01-02", "AVG_HUM": None},
                ]
            },
        }

        report = validate_payload(payload)

        self.assertFalse(report["ok"])
        self.assertEqual(report["nonnull_count"], {"AVG_HUM": 0})
        self.assertEqual(report["all_null_variables"], ["AVG_HUM"])
        self.assertEqual(report["usable_row_count"], 0)

    def test_openet_county_lookup_accepts_county_suffix(self):
        """County-based OpenET queries should work with or without a trailing 'County' suffix."""
        query = LocationCropQuery(full_oregon_gpkg="data/preliminary_or_field_geopackage.gpkg")

        direct = query.find_fields_by_county("Morrow")
        with_suffix = query.find_fields_by_county("Morrow County")

        self.assertEqual(len(direct), len(with_suffix))
        self.assertEqual(set(direct["OPENET_ID"]), set(with_suffix["OPENET_ID"]))

    def test_openet_alfalfa_area_query_by_county_returns_yearly_rows(self):
        """The Morrow County alfalfa acreage query should return annual rows instead of a false no-data result."""
        query = LocationCropQuery(full_oregon_gpkg="data/preliminary_or_field_geopackage.gpkg")

        result = query.query_variable_by_county(
            "Morrow County",
            variable="ACRES_FTR_GEOM",
            start_date="2014-01-01",
            end_date="2022-12-31",
            crop_filter="Alfalfa",
        )

        self.assertEqual(len(result), 9)
        self.assertEqual(result["datetime"].min().strftime("%Y-%m-%d"), "2014-01-01")
        self.assertEqual(result["datetime"].max().strftime("%Y-%m-%d"), "2022-01-01")
        self.assertTrue((result["ACRES_FTR_GEOM"] > 0).all())

    def test_morrow_crop_summary_still_lists_alfalfa(self):
        """The existing crop-summary flow should still surface Alfalfa for Morrow County."""
        query = LocationCropQuery(full_oregon_gpkg="data/preliminary_or_field_geopackage.gpkg")

        result = query.query_crops_by_county("Morrow County", year=2024)

        self.assertIn("Alfalfa", set(result["crop_name"]))

    def test_itype_categorical_counts_return_grouped_field_years(self):
        """ITYPE ranking queries should return category counts by year, not a single modal code."""
        query = LocationCropQuery(full_oregon_gpkg="data/preliminary_or_field_geopackage.gpkg")

        result = query.query_categorical_counts_by_location(
            location="Jefferson County",
            location_type="county",
            compare_by="ITYPE",
            start_date="2015-01-01",
            end_date="2021-12-31",
            crop_filter="Wheat",
        )

        self.assertGreater(len(result), 7)
        self.assertIn("field_count", result.columns)
        self.assertEqual(result["datetime"].min().strftime("%Y-%m-%d"), "2015-01-01")
        self.assertEqual(result["datetime"].max().strftime("%Y-%m-%d"), "2021-01-01")
        self.assertGreater(result["group"].nunique(), 1)
        self.assertTrue((result["field_count"] > 0).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
