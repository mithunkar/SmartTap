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

from core.data_fetcher import fetch_data, fetch_agrimet_data, fetch_openet_data, resolve_agrimet_location
from core.location_crop_query import LocationCropQuery
from core.validation import validate_payload


class TestDataFetcher(unittest.TestCase):
    """Test data fetching functionality"""
    
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
        """Test that invalid location raises error"""
        spec = {
            "dataset": "agrimet",
            "location": "invalid_location",
            "variables": ["OBM"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-10"
        }
        
        with self.assertRaises(ValueError):
            fetch_agrimet_data(spec)
    
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
        
        payload = fetch_agrimet_data(spec)
        records = payload["data"]["records"]
        
        # Verify all variables present
        first_record = records[0]
        self.assertIn("OBM", first_record)
        self.assertIn("PC", first_record)
        self.assertIn("SR", first_record)

    def test_agrimet_county_resolves_to_supported_local_station(self):
        """County mentions should resolve through station metadata to a local AgriMet dataset."""
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

        payload = fetch_agrimet_data(spec)
        self.assertEqual(payload["spec"]["location"], "corvallis")
        self.assertEqual(payload["spec"]["station_id"], "crvo")
        self.assertEqual(len(payload["data"]["records"]), 3)
    
    def test_openet_fetch(self):
        """Test OpenET data fetching (if data exists)"""
        from pathlib import Path
        openet_file = Path(__file__).parent.parent / "data" / "openet" / "huc_combined_long.csv"
        
        if not openet_file.exists():
            self.skipTest("OpenET data not available")
        
        spec = {
            "dataset": "openet",
            "openet_geo": "huc8",
            "huc8_code": "18010204",
            "variables": ["ETa"],
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
            "interval": "monthly"
        }
        
        payload = fetch_openet_data(spec)
        
        # Verify structure
        self.assertIn("spec", payload)
        self.assertIn("data", payload)
        self.assertIn("records", payload["data"])
        
        # Verify records exist
        records = payload["data"]["records"]
        self.assertGreater(len(records), 0, "Should have records")
        
        # Verify ETa field
        first_record = records[0]
        self.assertIn("datetime", first_record)
        self.assertIn("ETa", first_record)
    
    def test_router_agrimet(self):
        """Test main fetch_data router for AgriMet"""
        spec = {
            "dataset": "agrimet",
            "location": "corvallis",
            "variables": ["OBM"],
            "start_date": "2020-01-01",
            "end_date": "2020-01-05"
        }
        
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
        self.assertEqual(payload["spec"]["fetch_mode"], "api_fallback")
        self.assertEqual(payload["spec"]["station_id"], "ptro")
        self.assertEqual(payload["data"]["records"][0]["PEN_ET"], 1.1)

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
