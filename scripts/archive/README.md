# Archived Scripts

These scripts are not actively used by the main SmartTap system but are preserved for reference, development, or future use.

## Contents

### Data Processing / Conversion
- **`convert_openet_gpkg.py`** - Converts geopackage to CSV and long format
  - *Not needed*: SmartTap queries `.gpkg` files directly
  - May cause memory errors on large files
  - Useful only for external data analysis

- **`combine_openet_field.py`** - Combines multiple OpenET field data files
  - Legacy data processing utility
  
- **`combine_openet_huc.py`** - Combines multiple OpenET HUC data files
  - Legacy data processing utility

### Development / Testing
- **`agrimet_api_test.py`** - AgriMet API testing and station finder
  - Find closest weather station to coordinates
  - Fetch live data from stations
  - Used by example script below

- **`example_agrimet_usage.py`** - Example usage of agrimet_api_test.py
  - Demo code for developers
  - Shows how to use station finder programmatically

### Inspection / Analysis
- **`inspect_geopackage.py`** - Inspect geopackage structure
  - View layers, columns, and sample data
  - Useful for debugging data issues
  - Update `gpkg_path` variable to use

## Why These Were Archived

These scripts either:
1. Serve development/testing purposes only
2. Duplicate functionality available in SmartTap
3. Are for one-time data processing
4. May cause issues if run incorrectly (memory errors, etc.)

## When You Might Need These

- **New data format**: If OpenET changes their format, conversion scripts may be useful
- **API debugging**: Station finder helps troubleshoot AgriMet connections
- **Code examples**: Example scripts show patterns for working with these APIs
- **Data inspection**: When diagnosing issues with geopackage files
