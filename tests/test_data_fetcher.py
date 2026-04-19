#!/usr/bin/env python3
"""
Unit tests for data_fetcher module
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_fetcher import fetch_data, fetch_agrimet_data, fetch_openet_data, resolve_agrimet_location


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
        """Crop-filtered empty results should mention the crop instead of implying the whole location has no data."""

        class FakeLocationCropQuery:
            def __init__(self, *args, **kwargs):
                pass

            def query_variable_by_city(self, **kwargs):
                return __import__("pandas").DataFrame()

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
            with self.assertRaises(ValueError) as exc:
                fetch_openet_data(spec)

        self.assertEqual(
            str(exc.exception),
            "No OpenET data found for Cucumber fields near Corvallis for 2016-01-01 to 2024-12-31.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
