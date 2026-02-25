#!/usr/bin/env python3
"""
AgriMet Station Finder Tool

Helps users discover available AgriMet stations by state, region, or name.
"""

import sys
import os

# Add parent directory to path to import from core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agrimet_api import fetch_all_stations


def list_all_stations(state_filter=None):
    """List all available AgriMet stations, optionally filtered by state"""
    stations = fetch_all_stations()
    
    if state_filter:
        state_upper = state_filter.upper()
        stations = [s for s in stations if s['properties'].get('state', '').upper() == state_upper]
        print(f"\nAgriMet Stations in {state_upper}:")
    else:
        print(f"\nAll AgriMet Stations ({len(stations)} total):")
    
    print("=" * 80)
    print(f"{'ID':6} | {'State':5} | {'Station Name'}")
    print("-" * 80)
    
    for station in sorted(stations, key=lambda s: (s['properties'].get('state', ''), s['properties'].get('siteid', ''))):
        props = station['properties']
        site_id = props.get('siteid', 'N/A')
        state = props.get('state', '??')
        title = props.get('title', 'N/A')
        print(f"{site_id:6} | {state:5} | {title}")
    
    print(f"\nTotal: {len(stations)} stations")


def search_stations(query):
    """Search for stations by name or location"""
    stations = fetch_all_stations()
    query_lower = query.lower()
    
    matches = []
    for station in stations:
        title = station['properties'].get('title', '').lower()
        site_id = station['properties'].get('siteid', '').lower()
        
        if query_lower in title or query_lower in site_id:
            matches.append(station)
    
    if not matches:
        print(f"\nNo stations found matching '{query}'")
        return
    
    print(f"\nStations matching '{query}' ({len(matches)} found):")
    print("=" * 80)
    print(f"{'ID':6} | {'State':5} | {'Station Name'}")
    print("-" * 80)
    
    for station in matches:
        props = station['properties']
        coords = station['geometry']['coordinates']
        site_id = props.get('siteid', 'N/A')
        state = props.get('state', '??')
        title = props.get('title', 'N/A')
        print(f"{site_id:6} | {state:5} | {title}")
        print(f"         Location: {coords[1]:.4f}°N, {coords[0]:.4f}°W")


def show_usage():
    """Show usage information"""
    print("""
AgriMet Station Finder

Usage:
    python list_stations.py                    # List all stations
    python list_stations.py --state OR         # List Oregon stations
    python list_stations.py --search Boise     # Search for stations
    python list_stations.py --help             # Show this help

Examples:
    python list_stations.py --state ID         # Idaho stations
    python list_stations.py --search Corvallis # Find Corvallis stations
""")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # No arguments - list all
        list_all_stations()
    
    elif len(sys.argv) == 3:
        if sys.argv[1] == "--state":
            list_all_stations(state_filter=sys.argv[2])
        elif sys.argv[1] == "--search":
            search_stations(sys.argv[2])
        else:
            show_usage()
    
    elif "--help" in sys.argv or "-h" in sys.argv:
        show_usage()
    
    else:
        show_usage()
