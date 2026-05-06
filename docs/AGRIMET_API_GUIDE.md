# AgriMet API Integration Guide

## Overview

SmartTap now supports **real-time data fetching** from the USBR AgriMet API with **full access to all 265+ weather stations** across the Pacific Northwest. Query any location, any sensors, on-demand!

## 🎯 Full API Access

### ✨ What's New

- **265+ stations** available (previously limited to 5)
- **All sensor types** supported (not just temperature/precipitation)
- **Automatic station discovery** - just specify any city or station name
- **Intelligent suggestions** when station not found
- **Station search tool** to discover available locations

## Quick Start

### Enable API Mode

```bash
# Single query
AGRIMET_USE_API=1 python smarttap.py "Show temperature in Boise, Idaho in July 2023"

# Keep it enabled for your session
export AGRIMET_USE_API=1
python smarttap.py "Show precipitation in Hermiston last week"
```

### Discover Available Stations

```bash
# List all stations in a state
python scripts/list_stations.py --state OR
python scripts/list_stations.py --state ID
python scripts/list_stations.py --state WA

# Search for stations by name
python scripts/list_stations.py --search Boise
python scripts/list_stations.py --search Salem
python scripts/list_stations.py --search Portland

# List ALL stations
python scripts/list_stations.py
```

## Features

### ✅ Supported Locations

**ALL 265+ AgriMet stations across:**
- **Oregon** (78 stations) - Corvallis, Portland, Hood River, Hermiston, Klamath Falls, etc.
- **Idaho** (52 stations) - Boise, Twin Falls, Pocatello, etc.
- **Washington** (43 stations) - Yakima, Wenatchee, Pasco, etc.
- **Wyoming, Colorado, Montana, California, Nevada, Utah, and more!**

Use `python scripts/list_stations.py --state OR` to see all stations in a state.

### ✅ Supported Variables/Sensors

**SmartTap Standard Variables:**
- `OBM` - Average temperature
- `MX` - Max temperature
- `MN` - Min temperature
- `PC` - Precipitation
- `SR` - Solar radiation
- `WS` - Wind speed
- `TU/RH` - Humidity
- `ET` - Evapotranspiration

**Direct Sensor Codes:**
You can also specify ANY AgriMet sensor code directly:
- `mx`, `mn` - Temperature sensors
- `pp` - Precipitation
- `sr` - Solar radiation
- `ws` - Wind speed
- `rh` - Relative humidity
- `et`, `etos`, `etrs` - Evapotranspiration variants
- `pc` - Cumulative precipitation
- And many more! (Availability depends on station)

- **Multi-variable queries**: "temperature and precipitation"
- **Date ranges**: Any valid date range supported by AgriMet API
- **All visualization types**: Single-axis, dual-axis, faceted

### ⚠️ Limitations

1. **Data availability**: API data may not be available for very recent dates (within last few days) or very old dates
2. **Network required**: Requires internet connection to fetch data
3. **API rate limits**: No known limits, but avoid excessive requests
4. **Sensor coverage**: Some sensors may not be available at all stations

## How It Works

### Architecture

```
SmartTap Query
    ↓
data_fetcher.py checks AGRIMET_USE_API flag
    ↓
IfLocation Type | Examples | How It Works |
|---------------|----------|--------------|
| **City name** | "Boise", "Corvallis", "Hermiston" | Fuzzy matches station by city name |
| **Station ID** | "boii", "crvo", "hero" | Direct lookup by 4-letter code |
| **Partial name** | "Portland", "Salem" | Searches station titles |

**Popular Oregon Stations:**
- `crvo` - Corvallis
- `hoxo` - Hood River
- `kflo` - Klamath Falls
- `onto` - Ontario
- `ptro` - Pendleton
- `hero` - Hermiston
- `mdfo` - Medford
- `asto` - Astoria
- `beno` - Bend

**Popular Idaho Stations:**
- `boii` - Boise
- `twfi` - Twin Falls
- `pici` - Picabo

**Want more?** Run `python scripts/list_stations.py --state XX`
    ↓
Returns same payload format as local files
    ↓
Rest of pipeline works unchanged
```

### Station Mapping

| SmartTap Location | Station ID | Station Name | Distance |
|-------------------|------------|--------------|----------|
| corvallis | crvo | Corvallis, Oregon | 6.0 miles |
| hood river | hoxo | Hood River, Oregon | 1.5 miles |
| klamath falls | kflo | Klamath Falls, Oregon | 4.5 miles |
| ontario | onto | Ontario, Oregon | 4.5 miles |
| pendleton | ptro | Pendleton, Oregon | 9.5 miles |

### Sensor Mapping

| SmartTap Variable | Sensor Codes | Description |
|-Any city/location name
python smarttap.py "Show temperature in Boise, Idaho in July 2023"
python smarttap.py "Show temperature in Hermiston, Oregon in August 2023"
python smarttap.py "Show precipitation in Yakima, Washington last summer"

# By station ID (if you know it)
python smarttap.py "Show temperature at boii in July 2023"  # Boise
python smarttap.py "Show precipitation at hero in June 2023"  # Hermiston

# Multi-variable queries work!
pythoStation not found"

**Error**: `Station not found for 'XYZ'`

**Solutions**:
1. **Use the search tool**: `python scripts/list_stations.py --search XYZ`
2. **List stations by state**: `python scripts/list_stations.py --state OR`
3. **Try station ID**: Use 4-letter code instead of city name
4. **Check spelling**: "Corvallis" not "Corvalus"

The system will suggest similar stations when it finds partial matches!
python scripts/list_stations.py --state ID
export AGRIMET_USE_API=1

# Temperature queries
python smarttap.py "Show temperature in Corvallis in July 2023"
python smarttap.py "Max and min temperature in Hood River last summer"

# Precipitation
python smarttap.py "Show precipitation in Klamath Falls in 2023"
python smarttap.py "Daily rainfall in Pendleton from June to August 2023"

# Multi-variable
python smarttap.py "Temperature and solar radiation in Ontario in May 2023"
python smarttap.py "Compare precipitation and temperature in Corvallis"

# All variables work the same as with local files!
```

## Troubleshooting

### "No data returned from API"

**Possible causes**:
- Date range is too recent (try dates from 2023 or earlier)
- Station doesn't have that sensor
- Network connection issues

**Solution**: Try a different date range or check your internet connection
Tools & Utilities

### Station Finder Tool

Discover available stations before querying:

```bash
# List all Oregon stations
python scripts/list_stations.py --state OR

# List all Idaho stations
python scripts/list_stations.py --state ID

# Search for specific location
python scripts/list_stations.py --search Boise
python scripts/list_stations.py --search Hood

# See everything (265+ stations)
python scripts/list_stations.py
```

Output shows:
- Station ID (4-letter code)
- State
- Full station name
- Coordinates (for search results
- ✅ You don't want to manage local CSV files
- ✅ You're querying infrequently
- ✅ You want to save disk space
- ✅ You're prototyping or testing

### Use Local Files When:
- ✅ You need fast response times
- ✅ You're running many queries in batch
- ✅ You work offline
- ✅ You need consistent historical data
- ✅ You're running automated systems

## Code Reference

### Key Files
- `core/agrimet_api.py` - API client implementation
- `core/data_fetcher.py` - Routing logic (API vs local)
- `scripts/agrimet_api_test.py` - Low-level API utilities
- `scripts/example_agrimet_usage.py` - API usage examples

### Adding New Locations

To add a new AgriMet station:

1. Find the station using the station finder:
```python
from scripts.agrimet_api_test import find_closest_agrimet_station
result = find_closest_agrimet_station(latitude, longitude)
station_id = result['station_data']['properties']['siteid']
```

2. Add to `core/agrimet_api.py`:
```python
STATION_MAP = {
    # ... existing entries
    "new_location": "station_id",  # New entry
}
```

3. Add corresponding local CSV files (optional)

## API Documentation

**Base URL**: `https://www.usbr.gov/pn-bin/daily.pl`

**Parameters**:
- `list`: Station and sensor codes (e.g., "crvo mx,crvo mn")
- `start`: Start date (YYYY-MM-DD)
- `end`: End date (YYYY-MM-DD)
- `format`: Response format ("csv" or "html")

**Example Request**:
```
GET https://www.usbr.gov/pn-bin/daily.pl?list=crvo%20mx,crvo%20mn&start=2023-07-01&end=2023-07-31&format=csv
```

**Response**: CSV format with DateTime and sensor columns

## Testing

Test the API integration:

```bash
# Test API module directly
python core/agrimet_api.py

# Test with SmartTap
AGRIMET_USE_API=1 python smarttap.py "Show temperature in Corvallis in July 2023"

# Compare API vs local files
python smarttap.py "Show temperature in Corvallis in July 2023"  # Local
AGRIMET_USE_API=1 python smarttap.py "Show temperature in Corvallis in July 2023"  # API
```

## Future Enhancements

Potential improvements:
- [ ] Automatic fallback to local files if API fails
- [ ] Caching API responses to reduce redundant requests
- [ ] Support for more AgriMet stations
- [ ] Hourly data support (if available from API)
- [ ] Bulk data download/update tool
- [ ] API response validation and error handling improvements

---

**Questions?** Check the main [README](../README.md) or open an issue.
