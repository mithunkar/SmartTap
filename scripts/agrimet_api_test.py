"""
AgriMet Station Finder

This script finds the closest AgriMet weather station to given latitude and longitude coordinates.
It fetches station data from the USBR AgriMet API and calculates distances using the haversine formula.

Usage:
    python find_closest_agrimet_station.py

Author: Sean B. Higgins
Date: October 22, 2025
"""

import httpx
import json
import math
from typing import Dict, List, Tuple, Optional


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth using the haversine formula.
    
    Args:
        lat1, lon1: Latitude and longitude of first point in decimal degrees
        lat2, lon2: Latitude and longitude of second point in decimal degrees
    
    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of Earth in kilometers
    earth_radius_km = 6371.0
    
    return earth_radius_km * c


def fetch_agrimet_stations() -> Optional[List[Dict]]:
    """
    Fetch AgriMet station data from the USBR API.
    
    Returns:
        List of station features or None if request fails
    """
    url = "https://www.usbr.gov/pn/agrimet/agrimetmap/usbr_map.json"
    
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get('features', [])
    except httpx.HTTPError as e:
        print(f"Error fetching AgriMet station data: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        return None


def find_closest_station(target_lat: float, target_lon: float, stations: List[Dict]) -> Optional[Dict]:
    """
    Find the closest AgriMet station to the target coordinates.
    
    Args:
        target_lat: Target latitude in decimal degrees
        target_lon: Target longitude in decimal degrees
        stations: List of station features from the API
    
    Returns:
        Dictionary containing the closest station info and distance, or None if no stations
    """
    if not stations:
        return None
    
    closest_station = None
    min_distance = float('inf')
    
    for station in stations:
        try:
            # Extract coordinates from the station data
            coordinates = station['geometry']['coordinates']
            station_lon, station_lat = coordinates[0], coordinates[1]
            
            # Calculate distance
            distance = haversine_distance(target_lat, target_lon, station_lat, station_lon)
            
            if distance < min_distance:
                min_distance = distance
                closest_station = {
                    'station_data': station,
                    'distance_km': distance,
                    'distance_miles': distance * 0.621371  # Convert km to miles
                }
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error processing station data: {e}")
            continue
    
    return closest_station


def format_station_info(station_info: Dict) -> str:
    """
    Format station information for display.
    
    Args:
        station_info: Dictionary containing station data and distance
    
    Returns:
        Formatted string with station details
    """
    station = station_info['station_data']
    properties = station['properties']
    coordinates = station['geometry']['coordinates']
    
    info = f"""
Closest AgriMet Station Found:
==============================
Station ID: {properties.get('siteid', 'N/A')}
Title: {properties.get('title', 'N/A')}
State: {properties.get('state', 'N/A')}
Region: {properties.get('region', 'N/A')}
Installation Date: {properties.get('install', 'N/A')}
Coordinates: {coordinates[1]:.6f}°N, {coordinates[0]:.6f}°W
URL: {properties.get('url', 'N/A')}

Distance from target location:
- {station_info['distance_km']:.2f} km
- {station_info['distance_miles']:.2f} miles
"""
    return info

def get_data_from_station(station_id: str, sensors: list[str] = None, date_range: tuple[str, str] = None, format: str = "csv") -> Optional[str]:
    """
    Fetch daily sensor data from a specific AgriMet station using the GET method.

    Args:
        station_id: The site ID of the AgriMet station (e.g., "arao")
        sensors: List of sensor codes to retrieve (default is None, which retrieves all available sensors)
        date_range: Tuple of (start_date, end_date) for data retrieval (default is None to retrieve only data from the past 7 days)
        format: Format of the returned data ("csv" or "html")
    
    Returns:
        Data as a string in the specified format, or None if request fails
    """

    # IMPORTANT: If sensors is None, the API returns all available sensors for the specified station. However,
    # if a user specifies some sensors to gather data for, the sensor names will need to be included in the request.
    # Specifically, the 'list' parameter needs to be provided the sensor names as follows: <site ID> <sensor1>,<site ID> <sensor2>,...
    if sensors:
        sensor_list = ','.join([f"{station_id} {sensor}" for sensor in sensors])
        station_id = sensor_list

    base_url = "https://www.usbr.gov/pn-bin/daily.pl"
    if date_range:
        start_date, end_date = date_range
        params = {
            'list': station_id,
            'start': start_date,
            'end': end_date,
            'format': format
        }
    else:
        params = {
            'list': station_id,
            'format': format
        }
    
    try:
        response = httpx.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as e:
        print(f"Error fetching data for station {station_id}: {e}")
        return None

def get_coordinates_from_user() -> Tuple[float, float]:
    """
    Get latitude and longitude coordinates from user input.
    
    Returns:
        Tuple of (latitude, longitude) in decimal degrees
    """
    while True:
        try:
            lat_input = input("Enter latitude (decimal degrees, e.g., 42.954395): ").strip()
            lon_input = input("Enter longitude (decimal degrees, e.g., -112.825185): ").strip()
            
            latitude = float(lat_input)
            longitude = float(lon_input)
            
            # Basic validation
            if not (-90 <= latitude <= 90):
                print("Error: Latitude must be between -90 and 90 degrees.")
                continue
            
            if not (-180 <= longitude <= 180):
                print("Error: Longitude must be between -180 and 180 degrees.")
                continue
            
            return latitude, longitude
            
        except ValueError:
            print("Error: Please enter valid numeric coordinates.")
            continue


def find_closest_agrimet_station(latitude: float, longitude: float) -> Optional[Dict]:
    """
    Programmatic interface to find the closest AgriMet station.
    
    Args:
        latitude: Target latitude in decimal degrees
        longitude: Target longitude in decimal degrees
    
    Returns:
        Dictionary containing closest station info and distance, or None if not found
    """
    stations = fetch_agrimet_stations()
    if stations is None:
        return None
    
    return find_closest_station(latitude, longitude, stations)


def main():
    """
    Main function to run the AgriMet station finder.
    """
    print("AgriMet Station Finder")
    print("=" * 22)
    print("This tool finds the closest AgriMet weather station to your coordinates.\n")
    
    # Get target coordinates from user
    target_lat, target_lon = get_coordinates_from_user()
    print(f"\nSearching for closest station to: {target_lat:.6f}°N, {target_lon:.6f}°W")
    
    # Fetch station data
    print("Fetching AgriMet station data...")
    stations = fetch_agrimet_stations()
    
    if stations is None:
        print("Failed to fetch station data. Please check your internet connection and try again.")
        return
    
    if not stations:
        print("No AgriMet stations found in the data.")
        return
    
    print(f"Found {len(stations)} AgriMet stations. Calculating distances...")
    
    # Find closest station
    closest = find_closest_station(target_lat, target_lon, stations)
    
    if closest is None:
        print("Could not find any valid stations.")
        return
    
    # Display results
    print(format_station_info(closest))

    # Gather the most recent sensor data from the closest station
    station_id = closest['station_data']['properties'].get('siteid', None)

    if station_id:
        print(f"Fetching recent sensor data for station ID: {station_id}...\n")
        #sensors = ['pp', 'pu']  # Random sensors selected for example; set to None to get all available sensors
        sensors = None

        date_range = None  # Set to None to get all available data; or specify as ('YYYY-MM-DD', 'YYYY-MM-DD')
        #date_range = ('2025-10-14', '2025-10-27')  # Example date range

        sensor_data = get_data_from_station(station_id, sensors=sensors, date_range=date_range, format="csv")

        if sensor_data:
            print("Retrieved Sensor Data:")
            print("-" * 30)
            print(sensor_data)
        else:
            print("Could not retrieve sensor data for the station.")


if __name__ == "__main__":
    main()