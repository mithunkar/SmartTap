#!/usr/bin/env python3
"""
Multi-model evaluation for SmartTap
Tests different LLM models and compares accuracy and performance
"""

import time
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.config import SUPPORTED_MODELS, get_model_display_name, set_model_name, get_installed_models
from llm.interpretation import get_task_specification
from core.data_fetcher import fetch_data
from core.visualizer import png_bytes


class MultiModelEvaluator:
    """Evaluate multiple LLM models"""
    
    def __init__(self, models=None):
        self.models = models or SUPPORTED_MODELS
        self.results = {}
    
    def load_test_cases(self):
        """Load test cases from fixtures"""
        fixtures_path = Path(__file__).parent / "fixtures" / "test_cases.json"
        with open(fixtures_path) as f:
            test_data = json.load(f)
        return test_data["llm_parsing_tests"]
    
    def check_field_match(self, result, expected, field):
        """Check if a specific field matches expected value"""
        if field not in expected:
            return True
        
        if field not in result:
            return False
        
        expected_val = expected[field]
        actual_val = result[field]
        
        # Handle list comparison (order may vary)
        if isinstance(expected_val, list):
            return set(actual_val) == set(expected_val)
        else:
            return actual_val == expected_val
    
    def evaluate_model_accuracy(self, model_name, test_cases):
        """Evaluate a single model's parsing accuracy"""
        print(f"\nTesting: {get_model_display_name(model_name)}")
        print("   " + "-"*60)
        
        # Set the model for this test run
        set_model_name(model_name)
        
        correct = 0
        total = 0
        errors = []
        timings = []
        
        for test_case in test_cases:
            total += 1
            test_id = test_case["id"]
            query = test_case["query"]
            expected = test_case["expected"]
            
            try:
                start_time = time.time()
                result = get_task_specification(query)
                parse_time = time.time() - start_time
                timings.append(parse_time)
                
                # Check key fields
                matches = True
                failed_field = None
                for field in ["dataset", "location", "huc8_code", "variables"]:
                    if not self.check_field_match(result, expected, field):
                        matches = False
                        failed_field = field
                        break
                
                if matches:
                    correct += 1
                    print(f"   PASS {test_id} ({parse_time:.2f}s)")
                else:
                    print(f"   FAIL {test_id} - field '{failed_field}' mismatch")
                    errors.append({
                        "test_id": test_id,
                        "field": failed_field,
                        "expected": expected.get(failed_field),
                        "actual": result.get(failed_field)
                    })
                    
            except Exception as e:
                print(f"   ERROR {test_id} - exception: {str(e)}")
                errors.append({"test_id": test_id, "error": str(e)})
        
        accuracy = correct / total if total > 0 else 0
        avg_time = sum(timings) / len(timings) if timings else 0
        
        return {
            "model": model_name,
            "display_name": get_model_display_name(model_name),
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "errors": errors,
            "avg_parse_time": round(avg_time, 2),
            "parse_times": timings
        }
    
    def evaluate_model_performance(self, model_name, num_queries=3):
        """Evaluate model's end-to-end performance"""
        set_model_name(model_name)
        
        test_queries = [
            "Show me temperature in Corvallis for January 2020",
            "Show me ET in Klamath Falls for 2020",
            "Show me precipitation in Pendleton for July 2024",
        ][:num_queries]
        
        total_times = []
        parse_times = []
        
        for query in test_queries:
            try:
                # Parse
                parse_start = time.time()
                spec = get_task_specification(query)
                parse_time = time.time() - parse_start
                parse_times.append(parse_time)
                
                # Fetch & visualize
                total_start = time.time()
                payload = fetch_data(spec)
                png_data = png_bytes(payload)
                total_time = time.time() - total_start + parse_time
                total_times.append(total_time)
                
            except Exception as e:
                print(f"   Query failed: {e}")
        
        return {
            "avg_total_time": round(sum(total_times) / len(total_times), 2) if total_times else None,
            "avg_parse_time": round(sum(parse_times) / len(parse_times), 2) if parse_times else None,
        }
    
    def run_comparison(self, include_performance=False):
        """Run comparison across all models"""
        print("="*70)
        print("MULTI-MODEL EVALUATION")
        print("="*70)
        
        # Check which models are installed
        installed_models = get_installed_models()
        if installed_models:
            print(f"Installed models: {', '.join(installed_models)}")
        else:
            print("Could not detect installed models")
        
        # Check if any test models are missing
        missing = [m for m in self.models if m not in installed_models]
        if missing and installed_models:
            print(f"Missing models (will skip): {', '.join(missing[:3])}")
            if len(missing) > 3:
                print(f"   ... and {len(missing)-3} more")
            print(f"\nInstall missing models: ollama pull <model-name>")
        
        print(f"\nTesting {len(self.models)} models...")
        
        test_cases = self.load_test_cases()
        
        for model_name in self.models:
            try:
                # Test accuracy
                accuracy_result = self.evaluate_model_accuracy(model_name, test_cases)
                
                # Test performance (optional, takes longer)
                if include_performance:
                    print(f"   Running performance tests...")
                    perf_result = self.evaluate_model_performance(model_name)
                    accuracy_result.update(perf_result)
                
                self.results[model_name] = accuracy_result
                
            except Exception as e:
                print(f"   Model failed: {e}")
                self.results[model_name] = {
                    "model": model_name,
                    "error": str(e)
                }
        
        return self.results
    
    def print_summary(self):
        """Print comparison summary"""
        print("\n" + "="*70)
        print("COMPARISON SUMMARY")
        print("="*70)
        
        # Separate successful from failed models
        successful = [(name, data) for name, data in self.results.items() if "accuracy" in data]
        failed = [(name, data) for name, data in self.results.items() if "error" in data]
        
        if not successful and not failed:
            print("\nNo results to display.")
            return
        
        # Sort successful models by accuracy and speed
        sorted_results = sorted(
            successful,
            key=lambda x: (x[1]["accuracy"], -(x[1]["avg_parse_time"] or 999)),
            reverse=True
        )
        
        if sorted_results:
            print(f"\n{'Model':<30} {'Accuracy':<12} {'Avg Parse':<12} {'Grade':<10}")
            print("-"*70)
            
            for model_name, data in sorted_results:
                display_name = data["display_name"]
                accuracy = data["accuracy"]
                parse_time = data.get("avg_parse_time")
                
                # Grade
                if accuracy >= 0.95:
                    grade = "Excellent"
                elif accuracy >= 0.85:
                    grade = "Very Good"
                elif accuracy >= 0.70:
                    grade = "Good"
                else:
                    grade = "Fair"
                
                parse_time_str = f"{parse_time:>5.2f}s" if parse_time else "  N/A  "
                print(f"{display_name:<30} {accuracy:>6.1%}       {parse_time_str}       {grade}")
        
        # Show failed models
        if failed:
            print(f"\nFailed Models ({len(failed)}):")
            for model_name, data in failed:
                display_name = get_model_display_name(model_name)
                error = data.get("error", "Unknown error")
                if "not found" in error.lower():
                    print(f"   • {display_name} - Not installed (run: ollama pull {model_name})")
                else:
                    print(f"   • {display_name} - {error}")
        
        # Best model
        if sorted_results:
            best_model = sorted_results[0]
            print("\n" + "="*70)
            print(f"BEST MODEL: {best_model[1]['display_name']}")
            print(f"   Accuracy: {best_model[1]['accuracy']:.1%}")
            print(f"   Speed: {best_model[1]['avg_parse_time']:.2f}s average parse time")
            print(f"   Correct: {best_model[1]['correct']}/{best_model[1]['total']} test cases")
    
    def save_results(self, output_dir="evaluation_results"):
        """Save comparison results to JSON"""
        output_path = Path(__file__).parent.parent / output_dir
        output_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_path / f"model_comparison_{timestamp}.json"
        
        with open(output_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "models_tested": len(self.models),
                "results": self.results
            }, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")
        return output_file


def main():
    """Run multi-model evaluation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate multiple LLM models")
    parser.add_argument("--models", nargs="+", help="Specific models to test")
    parser.add_argument("--performance", action="store_true", help="Include performance tests")
    parser.add_argument("--quick", action="store_true", help="Test only 2-3 popular models")
    parser.add_argument("--auto-detect", action="store_true", help="Auto-detect and test only installed models")
    args = parser.parse_args()
    
    if args.auto_detect:
        installed = get_installed_models()
        if not installed:
            print("No models detected. Make sure ollama is running:")
            print("   ollama serve")
            print("   ollama pull gemma3")
            return 1
        models = installed
        print(f"Auto-detected {len(models)} installed models")
    elif args.quick:
        # Try common models that might be installed
        quick_options = ["gemma3:latest", "llama3.2:latest", "gemma2:2b", "llama3.2:3b", "phi3:mini"]
        installed = get_installed_models()
        if installed:
            # Use intersection of quick options and installed
            models = [m for m in quick_options if m in installed]
            if not models:
                # Fall back to first 2-3 installed
                models = installed[:3]
        else:
            models = quick_options[:3]
        print(f"Quick mode: testing {len(models)} models")
    elif args.models:
        models = args.models
    else:
        models = SUPPORTED_MODELS
    
    evaluator = MultiModelEvaluator(models=models)
    
    try:
        evaluator.run_comparison(include_performance=args.performance)
        evaluator.print_summary()
        evaluator.save_results()
    except KeyboardInterrupt:
        print("\n\nEvaluation interrupted")
        if evaluator.results:
            evaluator.print_summary()
            evaluator.save_results()
    except Exception as e:
        print(f"\nEvaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
