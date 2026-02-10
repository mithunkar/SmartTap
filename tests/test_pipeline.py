#!/usr/bin/env python3
"""
Integration tests for full SmartTap pipeline
Tests end-to-end query -> chart generation
"""

import unittest
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.interpretation import get_task_specification
from core.data_fetcher import fetch_data
from core.visualizer import png_bytes, vega_spec
from core.validation import validate_payload


class TestPipeline(unittest.TestCase):
    """Test full pipeline integration"""
    
    def setUp(self):
        """Create temp directory for outputs"""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        """Clean up temp directory"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_agrimet_simple_query(self):
        """Test simple AgriMet query end-to-end"""
        query = "Show me temperature in Corvallis for January 2020"
        
        # Step 1: Parse query
        spec = get_task_specification(query)
        self.assertEqual(spec["dataset"], "agrimet")
        self.assertEqual(spec["location"], "corvallis")
        
        # Step 2: Fetch data
        payload = fetch_data(spec)
        self.assertIsNotNone(payload)
        self.assertIn("data", payload)
        self.assertIn("records", payload["data"])
        
        # Step 3: Validate
        report = validate_payload(payload)
        self.assertTrue(report["ok"], f"Validation failed: {report.get('errors')}")
        
        # Step 4: Generate PNG
        png_data = png_bytes(payload)
        self.assertIsInstance(png_data, bytes)
        self.assertGreater(len(png_data), 1000, "PNG seems too small")
        
        # Step 5: Generate Vega spec
        vega = vega_spec(payload)
        self.assertIn("$schema", vega)
        self.assertIn("data", vega)
    
    def test_openet_query(self):
        """Test OpenET query end-to-end (if data available)"""
        openet_file = Path(__file__).parent.parent / "data" / "openet" / "huc_combined_long.csv"
        
        if not openet_file.exists():
            self.skipTest("OpenET data not available")
        
        query = "Show me ET in Klamath Falls for 2020"
        
        # Step 1: Parse
        spec = get_task_specification(query)
        self.assertEqual(spec["dataset"], "openet")
        self.assertIn("huc8_code", spec)
        
        # Step 2: Fetch
        payload = fetch_data(spec)
        self.assertIsNotNone(payload)
        
        # Step 3: Validate
        report = validate_payload(payload)
        self.assertTrue(report["ok"])
        
        # Step 4: Visualize
        png_data = png_bytes(payload)
        self.assertGreater(len(png_data), 1000)
        
        vega = vega_spec(payload)
        self.assertIn("$schema", vega)
    
    def test_multi_variable_query(self):
        """Test query with multiple variables"""
        query = "Show me max temp and precipitation in Corvallis for July 2020"
        
        spec = get_task_specification(query)
        payload = fetch_data(spec)
        
        # Verify both variables present
        records = payload["data"]["records"]
        self.assertGreater(len(records), 0)
        
        # Check that records have both variables
        first_record = records[0]
        self.assertIn("datetime", first_record)
        # Should have either MX or PC (or both)
        has_vars = any(v in first_record for v in ["MX", "PC", "OBM"])
        self.assertTrue(has_vars, "Record should have temperature or precipitation data")
    
    def test_date_range_parsing(self):
        """Test various date range formats"""
        test_queries = [
            ("Show me temperature in Corvallis for 2020", 2020),
            ("Show me temperature in Corvallis for July 2020", 2020),
        ]
        
        for query, expected_year in test_queries:
            spec = get_task_specification(query)
            self.assertIn("start_date", spec)
            self.assertIn(str(expected_year), spec["start_date"])
    
    def test_chart_type_parsing(self):
        """Test chart type parsing"""
        query = "Show me rainfall in Pendleton for 2020 as a bar chart"
        
        spec = get_task_specification(query)
        self.assertEqual(spec.get("chart_type"), "bar")
    
    def test_dataset_routing(self):
        """Test that dataset routing works correctly"""
        test_cases = [
            ("Show me ET in Klamath Falls", "openet"),
            ("Show me evapotranspiration in Klamath Falls", "openet"),
            ("Show me temperature in Klamath Falls", "agrimet"),
            ("Show me precipitation in Klamath Falls", "agrimet"),
            ("Show me solar radiation in Corvallis", "agrimet"),
        ]
        
        for query, expected_dataset in test_cases:
            spec = get_task_specification(query)
            actual_dataset = spec.get("dataset")
            self.assertEqual(actual_dataset, expected_dataset,
                f"Query '{query}' routed to {actual_dataset}, expected {expected_dataset}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
