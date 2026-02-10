#!/usr/bin/env python3
"""
Unit tests for data_fetcher module
"""

import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_fetcher import fetch_data, fetch_agrimet_data, fetch_openet_data


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
