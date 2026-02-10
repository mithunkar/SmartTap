#!/usr/bin/env python3
"""
Master test runner for SmartTap
Runs all tests and generates comprehensive report
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to sys.path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test discovery
test_dir = Path(__file__).parent

def run_all_tests():
    """Run all unit and integration tests"""
    print("="*70)
    print("SMARTTAP TEST SUITE")
    print("="*70)
    
    # Discover and run tests
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern="test_*.py")
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\nALL TESTS PASSED")
        return 0
    else:
        print("\nSOME TESTS FAILED")
        return 1


def run_evaluation():
    """Run performance and accuracy evaluation"""
    print("\n" + "="*70)
    print("RUNNING EVALUATION METRICS")
    print("="*70)
    
    # Import and run evaluation
    from evaluation_metrics import main as eval_main
    
    eval_main()


if __name__ == "__main__":
    # Run tests
    test_result = run_all_tests()
    
    # Run evaluation
    try:
        run_evaluation()
    except Exception as e:
        print(f"\nEvaluation metrics failed: {e}")
    
    sys.exit(test_result)
