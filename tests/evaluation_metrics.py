#!/usr/bin/env python3
"""
Performance and quality metrics for SmartTap evaluation
Measures response time, accuracy, and data quality
"""

import time
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.interpretation import get_task_specification
from llm.config import get_model_name, get_model_display_name
from core.data_fetcher import fetch_data
from core.visualizer import png_bytes, vega_spec
from core.validation import validate_payload


class PerformanceEvaluator:
    """Evaluate SmartTap performance metrics"""
    
    def __init__(self):
        self.results = []
    
    def measure_query_time(self, query: str) -> Dict:
        """Measure end-to-end query execution time"""
        start_time = time.time()
        
        try:
            # Parse
            parse_start = time.time()
            spec = get_task_specification(query)
            parse_time = time.time() - parse_start
            
            # Fetch
            fetch_start = time.time()
            payload = fetch_data(spec)
            fetch_time = time.time() - fetch_start
            
            # Validate
            validate_start = time.time()
            report = validate_payload(payload)
            validate_time = time.time() - validate_start
            
            # Visualize
            viz_start = time.time()
            png_data = png_bytes(payload)
            vega = vega_spec(payload)
            viz_time = time.time() - viz_start
            
            total_time = time.time() - start_time
            
            return {
                "success": True,
                "query": query,
                "total_time": round(total_time, 2),
                "parse_time": round(parse_time, 2),
                "fetch_time": round(fetch_time, 2),
                "validate_time": round(validate_time, 2),
                "viz_time": round(viz_time, 2),
                "record_count": len(payload["data"]["records"]),
                "png_size_kb": len(png_data) / 1024,
                "validation_ok": report["ok"],
                "warnings": len(report.get("warnings", [])),
                "dataset": spec.get("dataset"),
            }
            
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "total_time": time.time() - start_time
            }
    
    def run_benchmark_suite(self) -> Dict:
        """Run standard benchmark queries"""
        benchmark_queries = [
            "Show me temperature in Corvallis for January 2020",
            "Show me precipitation in Pendleton for 2020",
            "Show me max temp and rainfall in Hood River for July 2024",
            "Show me temperature in Corvallis from 2015 to 2020",
        ]
        
        # Add OpenET if available
        openet_file = Path(__file__).parent.parent / "data" / "openet" / "huc_combined_long.csv"
        if openet_file.exists():
            benchmark_queries.append("Show me ET in Klamath Falls for 2020")
        
        print("="*70)
        print("RUNNING PERFORMANCE BENCHMARKS")
        print("="*70)
        
        results = []
        for query in benchmark_queries:
            print(f"\n📊 Testing: {query}")
            result = self.measure_query_time(query)
            results.append(result)
            
            if result["success"]:
                print(f"   ✅ Success in {result['total_time']}s")
                print(f"      Parse: {result['parse_time']}s | Fetch: {result['fetch_time']}s | "
                      f"Viz: {result['viz_time']}s")
                print(f"      Records: {result['record_count']} | PNG: {result['png_size_kb']:.1f} KB")
                if result['warnings'] > 0:
                    print(f"      ⚠️  {result['warnings']} validation warnings")
            else:
                print(f"   ❌ Failed: {result['error']}")
        
        # Calculate statistics
        successful = [r for r in results if r["success"]]
        
        if successful:
            avg_time = sum(r["total_time"] for r in successful) / len(successful)
            max_time = max(r["total_time"] for r in successful)
            min_time = min(r["total_time"] for r in successful)
            
            print("\n" + "="*70)
            print("BENCHMARK SUMMARY")
            print("="*70)
            print(f"Successful: {len(successful)}/{len(results)}")
            print(f"Average time: {avg_time:.2f}s")
            print(f"Min time: {min_time:.2f}s")
            print(f"Max time: {max_time:.2f}s")
            
            # Check against thresholds
            if avg_time < 15:
                print("✅ Performance: GOOD (avg < 15s)")
            elif avg_time < 25:
                print("⚠️  Performance: ACCEPTABLE (avg < 25s)")
            else:
                print("❌ Performance: NEEDS IMPROVEMENT (avg >= 25s)")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "summary": {
                "total_tests": len(results),
                "successful": len(successful),
                "failed": len(results) - len(successful),
                "avg_time": avg_time if successful else None,
                "max_time": max_time if successful else None,
                "min_time": min_time if successful else None,
            }
        }
    
    def evaluate_llm_accuracy(self, test_cases: List[Dict]) -> Dict:
        """Evaluate LLM parsing accuracy"""
        print("\n" + "="*70)
        print("EVALUATING LLM PARSING ACCURACY")
        print("="*70)
        
        correct = 0
        total = 0
        errors = []
        
        for test_case in test_cases:
            total += 1
            query = test_case["query"]
            expected = test_case["expected"]
            
            try:
                result = get_task_specification(query)
                
                # Check key fields
                matches = True
                for key in ["dataset", "location", "huc8_code"]:
                    if key in expected:
                        if result.get(key) != expected[key]:
                            matches = False
                            errors.append({
                                "query": query,
                                "field": key,
                                "expected": expected[key],
                                "actual": result.get(key)
                            })
                            break
                
                # Check variables (order-independent)
                if "variables" in expected and matches:
                    expected_vars = set(expected["variables"])
                    actual_vars = set(result.get("variables", []))
                    if expected_vars != actual_vars:
                        matches = False
                        errors.append({
                            "query": query,
                            "field": "variables",
                            "expected": list(expected_vars),
                            "actual": list(actual_vars)
                        })
                
                if matches:
                    correct += 1
                    print(f"✅ {test_case['id']}")
                else:
                    print(f"❌ {test_case['id']}")
                    
            except Exception as e:
                print(f"❌ {test_case['id']}: {str(e)}")
                errors.append({"query": query, "error": str(e)})
        
        accuracy = correct / total if total > 0 else 0
        
        print(f"\n{'='*70}")
        print(f"ACCURACY: {correct}/{total} ({accuracy:.1%})")
        print(f"{'='*70}")
        
        if errors:
            print(f"\n{len(errors)} errors:")
            for err in errors[:5]:  # Show first 5
                print(f"  • {err}")
        
        return {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "errors": errors
        }


def main():
    """Run all evaluations"""
    # Show which model is being tested
    current_model = get_model_name()
    model_display = get_model_display_name(current_model)
    
    print(f"\n🤖 Testing Model: {model_display} ({current_model})")
    
    evaluator = PerformanceEvaluator()
    
    # 1. Performance benchmarks
    perf_results = evaluator.run_benchmark_suite()
    
    # 2. LLM accuracy (if test cases exist)
    fixtures_path = Path(__file__).parent / "fixtures" / "test_cases.json"
    if fixtures_path.exists():
        with open(fixtures_path) as f:
            test_data = json.load(f)
        
        accuracy_results = evaluator.evaluate_llm_accuracy(
            test_data["llm_parsing_tests"]
        )
    else:
        accuracy_results = {"note": "Test cases not found"}
    
    # 3. Save results
    output_dir = Path(__file__).parent.parent / "evaluation_results"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"evaluation_{timestamp}.json"
    
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "model": current_model,
            "model_display": model_display,
            "performance": perf_results,
            "accuracy": accuracy_results
        }, f, indent=2)
    
    print(f"\n📁 Results saved to: {output_file}")
    
    # Overall grade
    print("\n" + "="*70)
    print("OVERALL EVALUATION")
    print("="*70)
    
    if perf_results["summary"]["successful"] == perf_results["summary"]["total_tests"]:
        print("✅ Reliability: 100% success rate")
    else:
        success_rate = perf_results["summary"]["successful"] / perf_results["summary"]["total_tests"]
        print(f"⚠️  Reliability: {success_rate:.1%} success rate")
    
    if accuracy_results.get("accuracy"):
        acc = accuracy_results["accuracy"]
        if acc >= 0.9:
            print(f"✅ LLM Accuracy: {acc:.1%} (Excellent)")
        elif acc >= 0.7:
            print(f"⚠️  LLM Accuracy: {acc:.1%} (Good)")
        else:
            print(f"❌ LLM Accuracy: {acc:.1%} (Needs Improvement)")
    
    avg_time = perf_results["summary"].get("avg_time")
    if avg_time:
        if avg_time < 15:
            print(f"✅ Performance: {avg_time:.2f}s average (Fast)")
        elif avg_time < 25:
            print(f"⚠️  Performance: {avg_time:.2f}s average (Acceptable)")
        else:
            print(f"❌ Performance: {avg_time:.2f}s average (Slow)")


if __name__ == "__main__":
    main()
