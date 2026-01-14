import sys
import json
from pathlib import Path

from llm_interpretation_module import get_task_specification
from data_fetcher import fetch_data
from visualizer import png_bytes, vega_spec


def process_query(query: str):
    
    output_path = Path(".")
    
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")
    
    #step 1 - parse query with LLM
    print("Parsing query with LLM...")
    spec = get_task_specification(query)
    
    if spec.get("task") == "error":
        print(f"\nError: {spec.get('error_message', 'Invalid query')}")
        return None
    
    print(f"Parsed specification:")
    print(f"   Dataset: {spec.get('dataset')}")
    print(f"   Location: {spec.get('location')}")
    print(f"   Variables: {spec.get('variables')}")
    print(f"   Date range: {spec.get('start_date')} to {spec.get('end_date')}")
    print(f"   Chart type: {spec.get('chart_type')}")
    

    #step 2 - Fetch data
    print("\nStep 2/3: Fetching data from API...")
    try:
        payload = fetch_data(spec)
        print(f"Fetched {len(payload['data']['records'])} data points")
    except Exception as e:
        print(f"\nError fetching data: {e}")
        return None
    
    #step 3 - generate visualizations
    print("\nStep 3/3: Generating visualizations...")
    
    results = {}
    
    #generate png
    try:
        png_data = png_bytes(payload)
        png_file = output_path / "chart.png"
        with open(png_file, "wb") as f:
            f.write(png_data)
        results['png'] = str(png_file)
        print(f"Saved PNG chart: {png_file}")
    except Exception as e:
        print(f"Error generating PNG: {e}")
    
    #generate Vega-Lite spec
    try:
        vega = vega_spec(payload)
        vega_file = output_path / "chart_vega.json"
        with open(vega_file, "w") as f:
            json.dump(vega, f, indent=2)
        results['vega'] = str(vega_file)
        print(f"Saved Vega-Lite spec: {vega_file}")
        print(f"   View at: https://vega.github.io/editor/")
    except Exception as e:
        print(f"Error generating Vega spec: {e}")
    
    print(f"\n{'='*60}")
    print("Charts generated.")
    print(f"{'='*60}\n")
    
    return results


def main():
    if len(sys.argv) != 2:
        print("Usage: python smarttap.py \"your query\"")
        print("\nExamples:")
        print('  python smarttap.py "Show me rain in Corvallis for July 2024"')
        print('  python smarttap.py "Compare temperature in Hood River and Ontario"')
        sys.exit(1)
    
    query = sys.argv[1]
    process_query(query)


if __name__ == "__main__":
    main()
