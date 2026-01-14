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
- **Storage**: 55 CSV files in `data/` directory (5 locations x 11 years)

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

## Files

- `smarttap.py` - Main entry point
- `llm_interpretation_module.py` - Query parser using Ollama/Gemma3
- `data_fetcher.py` - Loads and filters CSV data
- `visualizer.py` - Creates charts (PNG and Vega-Lite)
- `fetch_data.py` - Data download script (one-time use)

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
