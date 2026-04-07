"""
Example usage of the AgriMet Station Finder

This script demonstrates how to use the find_closest_agrimet_station function
programmatically with predefined coordinates.
"""

from agrimet_api_test import find_closest_agrimet_station, format_station_info, get_data_from_station


def example_usage():
    """
    Example of how to use the AgriMet station finder programmatically.
    """
    # Example coordinates (Boise, Idaho area)
    example_lat = 43.6150
    example_lon = -116.2023
    
    print("Example: Finding closest AgriMet station to Boise, Idaho")
    print(f"Target coordinates: {example_lat}°N, {example_lon}°W\n")
    
    # Find the closest station
    result = find_closest_agrimet_station(example_lat, example_lon)
    
    if result:
        print(format_station_info(result))
    else:
        print("Could not find any AgriMet stations.")


def test_multiple_locations():
    """
    Test the function with multiple locations.
    """
    test_locations = [
        ("Boise, ID", 43.6150, -116.2023),
        ("Portland, OR", 45.5152, -122.6784),
        ("Denver, CO", 39.7392, -104.9903),
        ("Phoenix, AZ", 33.4484, -112.0740)
    ]
    
    print("Testing multiple locations:")
    print("=" * 40)
    
    for location_name, lat, lon in test_locations:
        print(f"\n{location_name} ({lat}°N, {lon}°W):")
        print("-" * 30)
        
        result = find_closest_agrimet_station(lat, lon)
        
        if result:
            station = result['station_data']
            properties = station['properties']
            print(f"Closest station: {properties.get('title', 'N/A')}")
            print(f"Station ID: {properties.get('siteid', 'N/A')}")
            print(f"Distance: {result['distance_km']:.1f} km ({result['distance_miles']:.1f} miles)")

            # Fetch and display recent sensor data
            station_id = properties.get('siteid')
            #sensors = ['pu', 'pp']  # Example sensors: daily precipitation and cumulative precipitation
            sensors = None  # Fetch all available sensors
            sensor_data = get_data_from_station(station_id, sensors=sensors, date_range=('2025-10-01', '2025-10-15'), format="csv")
            if sensor_data:
                print("Recent Sensor Data:")
                print("-" * 30)
                print(sensor_data)
            else:
                print("No sensor data available.")
        else:
            print("No station found")


if __name__ == "__main__":
    example_usage()
    print("\n" + "="*60 + "\n")
    test_multiple_locations()