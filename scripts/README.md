# SmartTap Scripts

Utility scripts for setup, maintenance, and data management.

## Active Utilities

### Setup
- **`extract_oregon_data.py`** - Extract the full Oregon geopackage from compressed archive
  ```bash
  python scripts/extract_oregon_data.py
  ```
  Extracts `data/archive/preliminary_or_field_geopackage.7z` → `data/preliminary_or_field_geopackage.gpkg`

### Data Management
- **`fetch_agrimet_data.py`** - Download AgriMet weather data
  ```bash
  python scripts/fetch_agrimet_data.py
  ```
  Fetches weather data from USBR API to populate `data/agrimet/` directory
  
  **When to use**: To refresh/update local weather CSV files

### Station Lookup
- **`list_stations.py`** - Find AgriMet weather stations
  ```bash
  # Search for stations
  python scripts/list_stations.py --search "Salem"
  
  # Browse by state
  python scripts/list_stations.py --state OR
  python scripts/list_stations.py --state WA
  ```
  Lists available weather stations by location or state

## Archived Scripts

Development and one-time use scripts are in [`archive/`](archive/README.md).

## Usage Notes

- Run scripts from project root: `python scripts/script_name.py`
- Most scripts have `--help` for usage info
- Scripts assume virtual environment is activated
