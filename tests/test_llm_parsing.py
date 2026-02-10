#!/usr/bin/env python3
"""
Test LLM query parsing accuracy
Evaluates how well the LLM converts natural language to specs
"""

import unittest
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.interpretation import get_task_specification


class TestLLMParsing(unittest.TestCase):
    """Test LLM query parsing accuracy"""
    
    @classmethod
    def setUpClass(cls):
        """Load test cases"""
        fixtures_path = Path(__file__).parent / "fixtures" / "test_cases.json"
        with open(fixtures_path) as f:
            cls.test_data = json.load(f)
        cls.test_cases = cls.test_data["llm_parsing_tests"]
    
    def _check_field(self, result, expected, field, test_id):
        """Helper to check a specific field"""
        if field in expected:
            self.assertIn(field, result, 
                f"Test {test_id}: Missing field '{field}'")
            
            expected_val = expected[field]
            actual_val = result[field]
            
            # Handle list comparison (order may vary)
            if isinstance(expected_val, list):
                self.assertEqual(set(actual_val), set(expected_val),
                    f"Test {test_id}: Field '{field}' mismatch")
            else:
                self.assertEqual(actual_val, expected_val,
                    f"Test {test_id}: Field '{field}' expected '{expected_val}', got '{actual_val}'")
    
    def test_parsing_accuracy(self):
        """Run all LLM parsing tests"""
        passed = 0
        failed = 0
        errors = []
        
        for test_case in self.test_cases:
            test_id = test_case["id"]
            query = test_case["query"]
            expected = test_case["expected"]
            
            try:
                result = get_task_specification(query)
                
                # Check key fields
                for field in ["dataset", "location", "variables", "openet_geo", "huc8_code"]:
                    try:
                        self._check_field(result, expected, field, test_id)
                    except AssertionError as e:
                        errors.append(f"FAIL {test_id}: {str(e)}")
                        failed += 1
                        break
                else:
                    print(f"PASS {test_id}")
                    passed += 1
                    
            except Exception as e:
                errors.append(f"ERROR {test_id}: {str(e)}")
                failed += 1
        
        # Print summary
        print("\n" + "="*70)
        print(f"LLM PARSING ACCURACY: {passed}/{passed+failed} ({100*passed/(passed+failed):.1f}%)")
        print("="*70)
        
        if errors:
            print("\nFailed tests:")
            for error in errors:
                print(f"  {error}")
        
        # Fail the test if accuracy is below threshold
        accuracy = passed / (passed + failed) if (passed + failed) > 0 else 0
        self.assertGreaterEqual(accuracy, 0.7, 
            f"LLM parsing accuracy {accuracy:.1%} is below 70% threshold")


if __name__ == "__main__":
    # Run with verbose output
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLLMParsing)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
