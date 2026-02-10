# SmartTap

Natural language interface for querying and visualizing Oregon agricultural weather and evapotranspiration data.

## Overview

SmartTap converts plain English questions into charts using AI. It intelligently routes queries to the appropriate dataset (AgriMet weather stations or OpenET agricultural data), loads local CSV files, and generates visualizations with automatic follow-up question suggestions.

## Architecture

1. **LLM Interpretation** (Ollama/Gemma3) - Parses natural language queries and routes to appropriate dataset
2. **Data Fetcher** - Loads CSV files from AgriMet weather stations or OpenET agricultural watershed data
3. **Validation** - Checks data quality and generates quality reports
4. **Visualizer** - Creates PNG charts and interactive Vega-Lite specifications
5. **Follow-up Generator** - Suggests relevant next questions based on the current visualization

## Quick Start

```bash
# 1. Ensure Ollama is running with Gemma3
ollama pull gemma3
ollama serve  # In a separate terminal

# 2. Run a query
python3 smarttap.py "Show me temperature in Corvallis for July 2024"

# 3. View the chart
open outputs/charts/chart_*_chart.png  # macOS
# or
xdg-open outputs/charts/chart_*_chart.png  # Linux

# 4. Try an OpenET query (Klamath Falls only)
python3 smarttap.py "Show me evapotranspiration in Klamath Falls for 2020"
```

## LLM Model Selection

SmartTap supports multiple LLM models. The default is **gemma2:2b**, but you can use any ollama-compatible model.

### Quick Start with Different Models

```bash
# Use default (gemma2:2b)
python3 smarttap.py "Show me temperature in Corvallis"

# Use Llama 3.2
export SMARTTAP_MODEL="llama3.2:3b"
python3 smarttap.py "Show me temperature in Corvallis"

# Use Phi-3 (fastest)
export SMARTTAP_MODEL="phi3:mini"
python3 smarttap.py "Show me temperature in Corvallis"
```

### Compare Models

Test multiple models and compare accuracy/performance:

```bash
# Install models
ollama pull gemma2:2b
ollama pull llama3.2:3b
ollama pull phi3:mini

# Quick comparison (3 popular models)
python3 tests/model_comparison.py --quick

# Full comparison (all supported models)
python3 tests/model_comparison.py

# With performance benchmarks
python3 tests/model_comparison.py --quick --performance
```

**See [MODEL_EVALUATION.md](MODEL_EVALUATION.md) for detailed model comparison guide.**

## Data Sources

### AgriMet Weather Stations
- **Years**: 2015-2025 (11 years)
- **Locations**: Corvallis, Pendleton, Hood River, Klamath Falls, Ontario
- **Source**: USBR AgriMet weather stations
- **Resolution**: Daily measurements
- **Storage**: 55 CSV files in `data/agrimet/` (5 locations × 11 years)

### OpenET Evapotranspiration (NEW!)
- **Years**: 1984-2024 (40 years)
- **Location**: Lost River watershed, Klamath Falls area (HUC8 18010204)
- **Coverage**: 203 agricultural fields
- **Source**: OpenET satellite-derived evapotranspiration
- **Resolution**: Monthly aggregates
- **Storage**: Combined dataset in `data/openet/huc_combined_long.csv` (124 MB, 893k records)

## Dataset Selection (Automatic)

SmartTap automatically routes your query to the correct dataset based on the **variable** you request:

| Variable Type | Dataset | Example Query |
|---------------|---------|---------------|
| **Evapotranspiration (ET)** | OpenET | "Show me ET in Klamath Falls for 2020" |
| **Temperature** | AgriMet | "Show me temperature in Klamath Falls" |
| **Precipitation** | AgriMet | "What was rainfall in Hood River?" |
| **Solar, Wind** | AgriMet | "Show me solar radiation in Corvallis" |

**Why?** AgriMet provides weather station measurements, while OpenET provides agricultural field water use calculations derived from satellite imagery.

## Available Variables

### AgriMet Variables
- **Temperature**: OBM (average), MX (maximum), MN (minimum)
- **Precipitation**: PC (daily rainfall in mm)
- **Solar**: SR (solar radiation in Langleys)
- **Wind**: WS (wind speed in mph)

### OpenET Variables (Klamath Falls only)
- **ETa**: Actual evapotranspiration (mm)
- **PPT**: Precipitation (mm)
- **AW**: Available water (mm)
- **WS_C**: Water stress coefficient
- **P_rz**: Root zone precipitation (mm)

## Usage

Basic query:
```bash
python3 smarttap.py "your question here"
```

### AgriMet Examples (Weather Station Data)
```bash
python3 smarttap.py "Show me temperature in Corvallis for July 2024"
python3 smarttap.py "What was rainfall in Hood River from 2020 to 2022?"
python3 smarttap.py "Show monthly average temperature in Klamath Falls for 2019 as a bar chart"
python3 smarttap.py "Compare precipitation in Pendleton for 2023"
```

### OpenET Examples (Evapotranspiration Data)
```bash
python3 smarttap.py "Show me evapotranspiration in Klamath Falls for 2020"
python3 smarttap.py "What was the ET in Klamath Falls last summer?"
python3 smarttap.py "Show me ET trends from 2015 to 2020"
```

**Note:** For the same location, you'll get different datasets:
- `"precipitation in Klamath Falls"` → AgriMet (weather station)
- `"evapotranspiration in Klamath Falls"` → OpenET (agricultural watershed)

## Output

Charts are automatically saved to timestamped directories in `outputs/`:

```
outputs/
├── charts/
│   ├── chart_YYYYMMDD_HHMMSS_chart.png          # PNG visualization
│   ├── chart_YYYYMMDD_HHMMSS_chart_vega.json    # Vega-Lite spec (paste into https://vega.github.io/editor/)
│   └── chart_YYYYMMDD_HHMMSS_meta.json          # Metadata (spec + view decision)
└── validation/
    ├── chart_YYYYMMDD_HHMMSS_validation.json    # Data quality report
    ├── chart_YYYYMMDD_HHMMSS_view.json          # Visualization layout decision
    └── chart_YYYYMMDD_HHMMSS_followups.json     # AI-generated follow-up questions
```

The terminal output displays:
- ✅ File paths for generated charts
- 📊 Data quality warnings (if any)
- 💡 Suggested follow-up questions
- 🔗 Direct link to view interactive chart

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

- Python 3.9+
- pandas
- geopandas (for OpenET data processing)
- matplotlib
- ollama (with Gemma3 model installed: `ollama pull gemma3`)
- requests

Install Python dependencies:
```bash
pip install pandas geopandas matplotlib requests ollama
```

## Setup OpenET Data (Optional)

The AgriMet weather data is already included. To enable OpenET evapotranspiration queries:

```bash
# 1. Convert GeoPackage to CSV (if you have _OpenET_Extracted.gpkg)
python3 scripts/convert_openet_gpkg.py --gpkg _OpenET_Extracted.gpkg

# 2. Combine into master dataset
python3 scripts/combine_openet_huc.py
```

This creates `data/openet/huc_combined_long.csv` (124 MB).

## Testing

SmartTap includes a comprehensive testing and evaluation framework. See [TESTING.md](TESTING.md) for detailed documentation.

### Quick Start

Run all tests and benchmarks:
```bash
python3 run_tests.py
```

### Individual Test Suites

```bash
# Unit tests - data fetching
python3 tests/test_data_fetcher.py

# LLM parsing accuracy
python3 tests/test_llm_parsing.py

# Dataset routing logic
python3 tests/test_llm_routing.py

# End-to-end integration tests
python3 tests/test_pipeline.py

# Performance & quality metrics
python3 tests/evaluation_metrics.py
```

### What Gets Tested

- **Data Fetching**: AgriMet and OpenET data loading, date filtering, error handling
- **LLM Parsing**: Natural language → JSON accuracy, dataset routing correctness
- **Integration**: Full pipeline from query to chart generation
- **Performance**: Response times, throughput, resource usage
- **Validation**: Data quality checks, spec validation

### Success Criteria

- Unit tests: 100% pass rate
- LLM accuracy: ≥70% (acceptable), ≥90% (excellent)
- Performance: Average query time < 15s
- Integration: Complete pipeline with no errors

Results are saved to `evaluation_results/` with timestamps for tracking over time.

## Features

✅ **Natural Language Queries** - Ask questions in plain English  
✅ **Smart Dataset Routing** - Automatically selects AgriMet or OpenET based on query  
✅ **Multi-format Output** - PNG charts + interactive Vega-Lite specs  
✅ **Data Validation** - Quality checks with warnings for missing/suspicious data  
✅ **AI Follow-ups** - Suggests relevant next questions  
✅ **Session Memory** - (Coming soon) Conversational refinement of charts  
✅ **Flexible Visualizations** - Single-axis, dual-axis, or faceted plots  

## Current Limitations

- **Single location per query** - Cannot compare multiple locations in one chart (e.g., "Corvallis vs Pendleton")
- **OpenET coverage** - Currently only Klamath Falls area (Lost River watershed HUC8 18010204)
  - Other locations use AgriMet only
  - To query ET: Must specify "Klamath Falls" AND "evapotranspiration/ET"
- **Wind speed** - AgriMet wind data appears to be all zeros (data quality issue)
- **Humidity** - Not available in current AgriMet dataset
- **Date parsing** - Works best with explicit dates (e.g., "2020" or "July 2024")  
  - Relative dates like "last week" may be inconsistent

## How It Works

### 1. Query Parsing (LLM)
The LLM (Gemma3 via Ollama) receives your natural language query and parses it into a structured JSON specification:

```json
{
  "task": "visualize_timeseries",
  "dataset": "agrimet",
  "location": "corvallis",
  "variables": ["OBM", "PC"],
  "start_date": "2020-01-01",
  "end_date": "2020-12-31",
  "interval": "daily",
  "chart_type": "line"
}
```

**Key Decision:** The LLM uses a **step-by-step approach** to determine the dataset:
1. Identify the variable requested (temperature, precipitation, ET, etc.)
2. Route to OpenET if variable is "ET/evapotranspiration", otherwise AgriMet
3. Map location to appropriate identifiers (station name for AgriMet, HUC8 code for OpenET)

### 2. Data Fetching
- **AgriMet**: Loads yearly CSV files for the specified location and date range
- **OpenET**: Queries the combined long-format CSV, filters by HUC8 code and date range

### 3. Validation
Checks for:
- Missing values (reports percentage per variable)
- Suspicious outliers (temperature < -60°F or > 130°F, etc.)
- Date continuity issues

### 4. Visualization Decision
Automatically chooses layout based on data:
- **Single-axis**: 1 variable, or multiple variables with similar scales
- **Dual-axis**: 2 variables with very different scales (ratio ≥ 5:1)
- **Faceted**: 3+ variables (small multiples)

### 5. Chart Generation
- **PNG**: Matplotlib static visualization
- **Vega-Lite**: Interactive JSON specification

### 6. Follow-up Questions
LLM analyzes the generated chart context and suggests 4 relevant follow-up questions.

## Troubleshooting

### "No module named 'ollama'"
```bash
pip install ollama
```

### "Connection refused" or LLM errors
Ollama server needs to be running:
```bash
ollama serve  # Keep this running in a separate terminal
```

### "No OpenET data found"
OpenET data is only available for Klamath Falls. Either:
1. Query a different variable (temperature, precipitation) which uses AgriMet
2. Process OpenET data: `python3 scripts/convert_openet_gpkg.py --gpkg <file>`, then `python3 scripts/combine_openet_huc.py`

### Charts have wrong title
The chart title is generated from the spec. If it says "Corvallis" but you queried "Klamath Falls", this was likely a validation fallback. Check `outputs/validation/*_validation.json` for details.

### Empty or unexpected results
1. Check the parsed spec in terminal output
2. Verify dates are in correct format (YYYY-MM-DD)
3. Look at `outputs/validation/*_validation.json` for data quality issues
4. Try a simpler query first: `"Show me temperature in Corvallis for 2020"`

## Contributing

This project was created for Smart-TAP (Smart Technology for Agricultural Precision). To contribute:

1. Test queries and report issues
2. Add support for more OpenET watersheds
3. Improve LLM prompt engineering for better query parsing
4. Add multi-location comparison features

## License

See LICENSE file for details.

---

**Project Status:** Active development. OpenET integration is new - expect bugs and improvements!
