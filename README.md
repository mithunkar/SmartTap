# SmartTap

Natural language interface for querying and visualizing Oregon agricultural weather data.

## Overview

SmartTap converts plain English questions about weather data into charts. It uses an LLM to parse queries, loads data from local CSV files, and generates visualizations.

## Architecture

1. **LLM Interpretation** - Parses natural language queries into structured JSON specifications
2. **Data Fetcher** - Loads appropriate CSV files based on location and date range
3. **Visualizer** - Generates PNG charts and Vega-Lite interactive specifications

## Data

- **Years**: 2015-2025 (11 years)
- **Locations**: Corvallis, Pendleton, Hood River, Klamath Falls, Ontario
- **Source**: USBR AgriMet weather stations
- **Storage**: 55 CSV files in `data/agrimet/` directory (5 locations x 11 years)

## Available Variables

- **Temperature**: OBM (average), MX (maximum), MN (minimum)
- **Precipitation**: PC (daily rainfall)
- **Solar**: SR (solar radiation)
- **Wind**: WS (wind speed)

## Usage

Basic query:
```bash
python3 smarttap.py "your question here"
```

Examples:
```bash
python3 smarttap.py "Show me temperature in Corvallis for July 2024"
python3 smarttap.py "What was rainfall in Hood River from 2020 to 2022?"
python3 smarttap.py "Show monthly average temperature in Klamath Falls for 2019 as a bar chart"
```

## Output

Each query generates two files:
- `chart.png` - Static matplotlib visualization
- `chart_vega.json` - Interactive Vega-Lite specification (paste into https://vega.github.io/editor/)

## Project Structure

```
SmartTap/
├── smarttap.py                    # Main entry point
├── core/                          # Core runtime modules
│   ├── data_fetcher.py           # Loads and filters CSV data
│   ├── visualizer.py             # Creates charts (PNG and Vega-Lite)
│   └── validation.py             # Data quality validation
├── llm/                           # LLM-powered features
│   ├── interpretation.py         # Query parser using Ollama/Gemma3
│   ├── followups.py              # Generates smart follow-up questions
│   └── session_update.py         # Updates specs from user feedback
├── scripts/                       # One-time setup/processing scripts
│   ├── fetch_agrimet_data.py     # Download AgriMet weather data
│   ├── convert_openet_gpkg.py    # Convert OpenET GeoPackage to CSV
│   ├── combine_openet_field.py   # Combine field-level OpenET data
│   ├── combine_openet_huc.py     # Combine HUC-level OpenET data
│   └── inspect_geopackage.py     # Utility to inspect GPKG layers
├── data/                          # Local data storage
│   ├── agrimet/                  # 55 weather CSV files (5 locations × 11 years)
│   └── openet/                   # Combined OpenET evapotranspiration data
└── tests/                         # Testing and examples
    ├── test_api.py               # OpenET API connectivity tests
    ├── test_visualizer.py        # Visualization tests
    └── fixtures/                 # Test data files
```

## Requirements

- Python 3.x
- pandas
- matplotlib
- ollama (with Gemma3 model)
- requests

## Limitations

- Single location per query (no multi-location comparisons yet)
- Wind speed data currently unavailable (all zeros)
- Humidity not in dataset
- Evapotranspiration not integrated
