"""
AgriMet API Client for SmartTap
Fetches weather data from USBR AgriMet API on-the-fly with support for ALL stations and sensors.

This module provides dynamic access to the full AgriMet network:
- 265+ weather stations across Pacific Northwest
- Any sensor/variable available from the API
- Automatic station discovery by location name
"""

import httpx
import pandas as pd
import math
import json
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from io import StringIO


# Global cache for station data (fetched once per session)
_STATIONS_CACHE: Optional[List[Dict]] = None

# Common SmartTap variable codes to AgriMet sensor codes mapping
# This is just a hint system - users can specify ANY sensor code
COMMON_SENSOR_MAP = {
    "OBM": ["mx", "mn"],       # Average temp (calculated from max/min)
    "MX": ["mx"],              # Max temperature
    "MN": ["mn"],              # Min temperature  
    "PC": ["pp"],              # Precipitation (daily)
    "SR": ["sr"],              # Solar radiation
    "WS": ["ws"],              # Wind speed
    "TU": ["rh"],              # Relative humidity
    "ET": ["et"],              # Evapotranspiration
    "RH": ["rh"],              # Relative humidity (alternative)
}

# Common location aliases for convenience
LOCATION_ALIASES = {
    "corvallis": "crvo",
    "hood river": "hoxo",
    "klamath falls": "kflo",
    "ontario": "onto",
    "pendleton": "ptro",
    "hermiston": "hero",
    "boise": "boii",
    "salem": "slmo",
    "medford": "mdfo",
    "bend": "beno",
}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    
    Args:
        lat1, lon1: Latitude and longitude of first point in decimal degrees
        lat2, lon2: Latitude and longitude of second point in decimal degrees
    
    Returns:
        Distance in kilometers
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371.0 * c


def fetch_all_stations() -> List[Dict]:
    """
    Fetch all AgriMet station data from the USBR API.
    Results are cached for the session.
    
    Returns:
        List of station features with properties and coordinates
    """
    global _STATIONS_CACHE
    
    if _STATIONS_CACHE is not None:
        return _STATIONS_CACHE
    
    url = "https://www.usbr.gov/pn/agrimet/agrimetmap/usbr_map.json"
    
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        _STATIONS_CACHE = data.get('features', [])
        print(f"✓ Fetched {len(_STATIONS_CACHE)} AgriMet stations from API")
        return _STATIONS_CACHE
    except httpx.HTTPError as e:
        print(f"Error fetching AgriMet station list: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing station JSON: {e}")
        return []


def find_station_by_name(location: str) -> Optional[Dict]:
    """
    Find an AgriMet station by location name (city, station name, or station ID).
    
    Args:
        location: Location name, station name, or station ID
        
    Returns:
        Station data dict or None if not found
    """
    location_lower = location.lower().strip()
    
    # Check aliases first
    if location_lower in LOCATION_ALIASES:
        station_id = LOCATION_ALIASES[location_lower]
        stations = fetch_all_stations()
        for station in stations:
            if station['properties'].get('siteid', '').lower() == station_id.lower():
                return station
    
    stations = fetch_all_stations()
    
    # Try exact station ID match
    for station in stations:
        site_id = station['properties'].get('siteid', '').lower()
        if site_id == location_lower:
            return station
    
    # Try fuzzy match on title
    for station in stations:
        title = station['properties'].get('title', '').lower()
        if location_lower in title:
            return station
    
    return None


def find_closest_station(lat: float, lon: float, state: Optional[str] = None) -> Optional[Dict]:
    """
    Find the closest AgriMet station to given coordinates.
    
    Args:
        lat: Target latitude
        lon: Target longitude
        state: Optional state filter (e.g., 'OR', 'ID', 'WA')
        
    Returns:
        Station data dict or None
    """
    stations = fetch_all_stations()
    
    if state:
        state_upper = state.upper()
        stations = [s for s in stations if s['properties'].get('state', '').upper() == state_upper]
    
    if not stations:
        return None
    
    closest = None
    min_distance = float('inf')
    
    for station in stations:
        try:
            coords = station['geometry']['coordinates']
            station_lon, station_lat = coords[0], coords[1]
            distance = haversine_distance(lat, lon, station_lat, station_lon)
            
            if distance < min_distance:
                min_distance = distance
                closest = station
        except (KeyError, IndexError, TypeError):
            continue
    
    return closest


def get_data_from_station(
    station_id: str, 
    sensors: Optional[List[str]] = None, 
    date_range: Optional[Tuple[str, str]] = None, 
    format: str = "csv"
) -> Optional[str]:
    """
    Fetch daily sensor data from a specific AgriMet station.

    Args:
        station_id: The site ID of the AgriMet station
        sensors: List of sensor codes to retrieve (None = all sensors)
        date_range: Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
        format: Response format ("csv" or "html")
    
    Returns:
        Data as CSV string, or None if request fails
    """
    if sensors:
        sensor_list = ','.join([f"{station_id} {sensor}" for sensor in sensors])
        station_param = sensor_list
    else:
        station_param = station_id

    base_url = "https://www.usbr.gov/pn-bin/daily.pl"
    
    if date_range:
        start_date, end_date = date_range
        params = {
            'list': station_param,
            'start': start_date,
            'end': end_date,
            'format': format
        }
    else:
        params = {
            'list': station_param,
            'format': format
        }
    
    try:
        response = httpx.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as e:
        print(f"Error fetching data for station {station_id}: {e}")
        return None


def parse_agrimet_csv(csv_text: str) -> pd.DataFrame:
    """
    Parse the CSV response from AgriMet API into a pandas DataFrame.
    
    Args:
        csv_text: Raw CSV text from API
        
    Returns:
        DataFrame with parsed data
    """
    if not csv_text:
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(StringIO(csv_text), comment='#')
        
        # Convert DateTime column to date
        if 'DateTime' in df.columns:
            df['date'] = pd.to_datetime(df['DateTime'], errors='coerce')
        elif 'DATETIME' in df.columns:
            df['date'] = pd.to_datetime(df['DATETIME'], errors='coerce')
        elif 'DATE' in df.columns:
            df['date'] = pd.to_datetime(df['DATE'], errors='coerce')
        else:
            first_col = df.columns[0]
            if first_col.upper() not in ['SITEID', 'STATION']:
                df['date'] = pd.to_datetime(df[first_col], errors='coerce')
        
        return df
    except Exception as e:
        print(f"Error parsing AgriMet CSV: {e}")
        return pd.DataFrame()


def fetch_agrimet_api_data(
    location: str,
    variables: List[str],
    start_date: str,
    end_date: str
) -> pd.DataFrame:
    """
    Fetch AgriMet data from API for ANY location and variables.
    Automatically finds the appropriate station and fetches requested sensors.
    
    Args:
        location: Location name, station name, or station ID
        variables: List of SmartTap variable codes or sensor codes
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
    
    Returns:
        DataFrame with date and sensor columns
    """
    location_clean = location.strip()
    
    # Try to find station by name/ID
    station = find_station_by_name(location_clean)
    
    if not station:
        # Suggest alternatives
        stations = fetch_all_stations()
        location_lower = location_clean.lower()
        similar = [s for s in stations if location_lower in s['properties'].get('title', '').lower()]
        
        if similar:
            suggestions = [f"  - {s['properties'].get('siteid')} | {s['properties'].get('title')}" 
                          for s in similar[:10]]
            raise ValueError(
                f"Station not found for '{location}'. Did you mean one of these?\n" +
                "\n".join(suggestions)
            )
        else:
            # Show some nearby Oregon stations as hint
            or_stations = [s for s in stations if s['properties'].get('state') == 'OR'][:10]
            suggestions = [f"  - {s['properties'].get('siteid')} | {s['properties'].get('title')}" 
                          for s in or_stations]
            raise ValueError(
                f"Station not found for '{location}'.\n"
                f"Try a station ID (e.g., 'crvo') or city name. Some Oregon stations:\n" +
                "\n".join(suggestions)
            )
    
    # Extract station info
    station_id = station['properties'].get('siteid')
    station_title = station['properties'].get('title', location)
    station_state = station['properties'].get('state', '')
    coords = station['geometry']['coordinates']
    
    print(f"✓ Found: {station_title} ({station_id}, {station_state})")
    print(f"  Location: {coords[1]:.4f}°N, {coords[0]:.4f}°W")
    
    # Map SmartTap variables to sensor codes
    sensors_needed = set()
    unmapped_vars = []
    
    for var in variables:
        var_upper = var.upper()
        if var_upper in COMMON_SENSOR_MAP:
            # Known SmartTap variable
            sensors_needed.update(COMMON_SENSOR_MAP[var_upper])
        else:
            # Treat as direct sensor code
            sensors_needed.add(var.lower())
            unmapped_vars.append(var)
    
    # Always fetch mx and mn for temperature calculations
    sensors_needed.update(['mx', 'mn'])
    sensors_list = sorted(list(sensors_needed))
    
    if unmapped_vars:
        print(f"  Note: Treating {unmapped_vars} as direct sensor codes")
    
    print(f"  Sensors requested: {sensors_list}")
    print(f"  Date range: {start_date} to {end_date}")
    
    # Fetch data from API
    csv_text = get_data_from_station(
        station_id=station_id,
        sensors=sensors_list,
        date_range=(start_date, end_date),
        format="csv"
    )
    
    if not csv_text:
        raise ValueError(f"Failed to fetch data from AgriMet API for station {station_id}")
    
    # Parse CSV
    df = parse_agrimet_csv(csv_text)
    
    if df.empty:
        raise ValueError(f"No data returned from AgriMet API for {location}")
    
    # Convert sensor columns to SmartTap format
    # API returns columns with format: stationid_sensor (e.g., crvo_mx)
    result = pd.DataFrame({'date': df['date']})
    
    # Find sensor columns
    mx_col = mn_col = pp_col = sr_col = ws_col = None
    
    for col in df.columns:
        col_lower = col.lower()
        if '_mx' in col_lower or col_lower == 'mx':
            mx_col = col
        elif '_mn' in col_lower or col_lower == 'mn':
            mn_col = col
        elif '_pp' in col_lower or col_lower == 'pp':
            pp_col = col
        elif '_sr' in col_lower or col_lower == 'sr':
            sr_col = col
        elif '_ws' in col_lower or col_lower == 'ws':
            ws_col = col
    
    result['max_temp_f'] = pd.to_numeric(df[mx_col], errors='coerce') if mx_col else None
    result['min_temp_f'] = pd.to_numeric(df[mn_col], errors='coerce') if mn_col else None
    result['daily_precip_in'] = pd.to_numeric(df[pp_col], errors='coerce').fillna(0.0) if pp_col else 0.0
    result['solar_langley'] = pd.to_numeric(df[sr_col], errors='coerce') if sr_col else None
    result['wind_speed_mph'] = pd.to_numeric(df[ws_col], errors='coerce') if ws_col else None
    
    result['location'] = station_title
    result['cum_precip_in'] = 0.0
    
    # Drop rows with invalid dates
    result = result.dropna(subset=['date'])
    
    # Check for empty data and warn
    data_cols = ['max_temp_f', 'min_temp_f', 'daily_precip_in', 'solar_langley', 'wind_speed_mph']
    empty_cols = [col for col in data_cols if result[col].isna().all() or (result[col] == 0).all()]
    
    if empty_cols:
        print(f"  ⚠️  Warning: No data available for: {', '.join(empty_cols)}")
        print(f"      This station may not have these sensors or data for this period.")
    
    print(f"  ✓ Retrieved {len(result)} records")
    
    return result


if __name__ == "__main__":
    print("=" * 70)
    print("AgriMet API - Enhanced Access Test")
    print("=" * 70)
    
    # Test 1: List available stations
    print("\n[TEST 1] Fetching all available stations...")
    stations = fetch_all_stations()
    print(f"  Total stations: {len(stations)}")
    
    or_stations = [s for s in stations if s['properties'].get('state') == 'OR']
    print(f"\n  Oregon stations (showing first 10 of {len(or_stations)}):")
    for i, s in enumerate(or_stations[:10]):
        props = s['properties']
        print(f"  {i+1:2}. {props.get('siteid'):6} | {props.get('title', 'N/A')}")
    
    # Test 2: Find stations by various methods
    print("\n[TEST 2] Testing station search...")
    
    test_searches = ["Corvallis", "boii", "Hermiston", "Salem"]
    for search_term in test_searches:
        station = find_station_by_name(search_term)
        if station:
            print(f"  '{search_term:12}' → {station['properties'].get('siteid'):6} | {station['properties'].get('title')}")
        else:
            print(f"  '{search_term:12}' → Not found")
    
    # Test 3: Fetch data
    print("\n[TEST 3] Fetching data from different locations...")
    
    test_cases = [
        ("Corvallis", ["OBM", "PC"], "2023-07-01", "2023-07-05"),
        ("boii", ["mx", "mn", "sr"], "2023-06-15", "2023-06-20"),
    ]
    
    for location, variables, start, end in test_cases:
        print(f"\n  Query: {location} | {variables} | {start} to {end}")
        try:
            df = fetch_agrimet_api_data(location, variables, start, end)
            print(f"  Success: {len(df)} records retrieved")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 70)
