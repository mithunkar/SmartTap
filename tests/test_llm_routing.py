#!/usr/bin/env python3
"""
Test LLM routing logic for AgriMet vs OpenET datasets
"""

from llm.interpretation import get_task_specification
import json

def test_routing():
    queries = [
        ('Show me precipitation in Klamath Falls for 2020', 'agrimet'),
        ('Show me evapotranspiration in Klamath Falls for 2020', 'openet'),
        ('What was the ET in Klamath Falls last year?', 'openet'),
        ('Show me temperature in Klamath Falls', 'agrimet'),
    ]
    
    print("="*70)
    print("TESTING LLM DATASET ROUTING")
    print("="*70)
    
    for query, expected_dataset in queries:
        print(f'\n🔍 Query: "{query}"')
        print(f'   Expected: {expected_dataset}')
        
        try:
            result = get_task_specification(query)
            actual_dataset = result.get('dataset', 'N/A')
            
            # Check for errors first
            if 'error' in result:
                print(f'   ❌ ERROR: {result.get("error")}')
                print(f'      Details: {result.get("details")}')
                print(f'      Raw response: {result.get("raw", "N/A")[:200]}...')
                continue
            
            # Check if routing is correct
            if actual_dataset == expected_dataset:
                print(f'   ✅ PASS: {actual_dataset}')
            else:
                print(f'   ❌ FAIL: Got {actual_dataset}, expected {expected_dataset}')
                # Show full result for debugging
                if actual_dataset == 'N/A':
                    print(f'      DEBUG: Full result = {json.dumps(result, indent=8)}')
            
            # Show OpenET-specific fields
            if actual_dataset == 'openet':
                print(f'      HUC8: {result.get("huc8_code", "MISSING")}')
                print(f'      Geo: {result.get("openet_geo", "MISSING")}')
            elif actual_dataset == 'agrimet':
                print(f'      Location: {result.get("location", "MISSING")}')
            
            print(f'      Variables: {result.get("variables", [])}')
            print(f'      Interval: {result.get("interval", "N/A")}')
            
        except Exception as e:
            print(f'   ❌ ERROR: {e}')
    
    print("\n" + "="*70)
    print("SUMMARY: Dataset selection based on VARIABLE type:")
    print("  • 'ET' or 'evapotranspiration' → OpenET (agricultural watershed)")
    print("  • Other weather vars → AgriMet (weather station)")
    print("="*70)

if __name__ == "__main__":
    test_routing()
