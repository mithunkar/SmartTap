"""
Data Fetcher Module for SmartTap
Loads pre-downloaded data from local CSV files.
"""

import pandas as pd
from typing import Dict, Any
from pathlib import Path

#base data directory
DATA_DIR = Path(__file__).parent / "data"

#location name to file prefix mapping
LOCATION_PREFIXES = {
    "corvallis": "corvallis_weather",
    "pendleton": "pendleton_weather",
    "hood river": "hood_river_weather",
    "klamath falls": "klamath_falls_weather",
    "ontario": "ontario_weather"
}


def get_data_files_for_range(location: str, start_date: str, end_date: str) -> list:
    """
    Get list of CSV files needed to cover the date range.
    
    Args:
        location: Location name
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        
    Returns:
        List of Path objects for CSV files to load
    """
    if location not in LOCATION_PREFIXES:
        raise ValueError(f"Unknown location: {location}. Available: {list(LOCATION_PREFIXES.keys())}")
    
    start_year = int(start_date.split('-')[0]) if start_date else 2015
    end_year = int(end_date.split('-')[0]) if end_date else 2025
    
    prefix = LOCATION_PREFIXES[location]
    files = []
    
    for year in range(start_year, end_year + 1):
        file_path = DATA_DIR / f"{prefix}_{year}.csv"
        if file_path.exists():
            files.append(file_path)
    
    return files


def fetch_agrimet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load weather data from local CSV files.
    
    Args:
        spec: Task specification with location, variables, dates, interval
        
    Returns:
        Dictionary with 'spec' and 'data' keys for visualization
    """
    location = spec.get("location", "corvallis")
    variables = spec.get("variables", [])
    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    interval = spec.get("interval", "daily")
    
    #get the appropriate data files for the date range
    csv_files = get_data_files_for_range(location, start_date, end_date)
    
    if not csv_files:
        raise FileNotFoundError(f"No data files found for {location} in date range {start_date} to {end_date}")
    
    print(f"Loading data from {len(csv_files)} file(s) for {location}...")
    
    try:
        #read and combine all CSV files
        dfs = []
        for csv_file in csv_files:
            df_year = pd.read_csv(csv_file)
            df_year['date'] = pd.to_datetime(df_year['date'])
            dfs.append(df_year)
        
        df = pd.concat(dfs, ignore_index=True)
        df = df.sort_values('date').reset_index(drop=True)
        
        #filter by date range
        if start_date:
            df = df[df['date'] >= start_date]
        if end_date:
            df = df[df['date'] <= end_date]
        
        if df.empty:
            raise ValueError(f"No data found for date range {start_date} to {end_date}")
        
        #rename date to datetime for consistency
        df = df.rename(columns={'date': 'datetime'})
        
        #process variables
        result_df = pd.DataFrame({'datetime': df['datetime']})
        
        for var in variables:
                    # ✅ FAIL FAST: ensure requested variables were actually produced
            

            

            if var == "OBM":
                #calculate average temperature from min/max (keep in Fahrenheit)
                result_df['OBM'] = ((df['max_temp_f'] + df['min_temp_f']) / 2).round(2)
            elif var == "MX":
                # maximum temperature (keep in Fahrenheit)
                result_df['MX'] = df['max_temp_f'].round(2)
            elif var == "MN":
                # minimum temperature (keep in Fahrenheit)
                result_df['MN'] = df['min_temp_f'].round(2)
            elif var == "PC":
                #use daily precipitation (convert from inches to mm)
                result_df['PC'] = (df['daily_precip_in'] * 25.4).round(2)
            elif var == "SR":
                #solar radiation (keep in Langleys)
                result_df['SR'] = df['solar_langley'].round(2)
            elif var == "WS":
                #wind speed (keep in mph)
                result_df['WS'] = df['wind_speed_mph'].round(2)
            elif var == "TU":
                #humidity not available in current CSV
                print(f"{var} (Humidity) not available in local data, skipping")
            else:
                print(f"Variable {var} not recognized")
            
        requested = variables or []
        present = set(result_df.columns) - {"datetime"}
        missing = [v for v in requested if v not in present]

        if missing:
                raise ValueError(
                    f"Requested variables missing from local agrimet data: {missing}. "
                    f"Present: {sorted(present)}"
                )
        
        # Handle intervals
        if interval == "monthly":
            result_df['month'] = result_df['datetime'].dt.to_period('M')
            agg_dict = {col: 'mean' for col in result_df.columns if col not in ['datetime', 'month']}
            result_df = result_df.groupby('month').agg(agg_dict).reset_index()
            result_df['datetime'] = result_df['month'].dt.to_timestamp()
            result_df = result_df.drop('month', axis=1)
        elif interval == "hourly":
            print("Local data is daily only, returning daily data")
        
        # Convert to records for payload
        records = result_df.to_dict(orient='records')
        
        print(f"Loaded {len(records)} records")
        
        return {
            "spec": spec,
            "data": {"records": records}
        }
        
    except Exception as e:
        print(f"Error loading local data: {e}")
        raise


def fetch_openet_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load evapotranspiration data from local files (placeholder).
    
    Args:
        spec: Task specification with location, dates, interval
        
    Returns:
        Dictionary with 'spec' and 'data' keys for visualization
    """
    print("OpenET data not available locally - generating sample data")
    
    # For now, generate sample ET data
    # In the future, you can add actual ET data to your local files

    requested_vars = spec.get("variables", []) or []
    unsupported = [v for v in requested_vars if v != "ET"]
    if unsupported:
        raise ValueError(
            f"OpenET placeholder only supports ET locally. "
            f"Requested unsupported variables: {unsupported}. "
            f"Tip: run the query without those variables, or use dataset='agrimet' for temps/rain."
        )


    start_date = spec.get("start_date")
    end_date = spec.get("end_date")
    
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # Sample ET values (typical range 2-8 mm/day)
    import numpy as np
    np.random.seed(42)
    et_values = np.random.uniform(2.0, 6.0, len(date_range)).round(2)
    
    df = pd.DataFrame({
        'datetime': date_range,
        'ET': et_values
    })
    
    records = df.to_dict(orient='records')
    
    print(f"Generated {len(records)} sample ET records")
    
    return {
        "spec": spec,
        "data": {"records": records}
    }


def fetch_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main data fetching function that routes to appropriate data source.
    
    Args:
        spec: Task specification from LLM interpretation
        
    Returns:
        Payload dictionary ready for visualization
    """
    if spec.get("task") == "error":
        raise ValueError(f"Error in spec: {spec.get('error_message')}")
    
    dataset = spec.get("dataset", "agrimet")
    
    if dataset == "openet":
        return fetch_openet_data(spec)
    elif dataset == "agrimet":
        return fetch_agrimet_data(spec)
    else:
        raise ValueError(f"Unknown dataset: {dataset}")


if __name__ == "__main__":
    # Test the data fetcher
    test_spec = {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "corvallis",
        "variables": ["OBM", "PC"],
        "start_date": "2024-07-01",
        "end_date": "2024-07-05",
        "interval": "daily",
        "chart_type": "line"
    }
    
    print("Testing data fetcher with local files...")
    payload = fetch_data(test_spec)
    print(f"Loaded {len(payload['data']['records'])} records")
    print(f"Sample: {payload['data']['records'][0]}")
    print(f"\nAll records:")
    for record in payload['data']['records']:
        print(f"  {record}")
