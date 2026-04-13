# SmartTap

SmartTap is a small Python app for turning plain-English requests about Oregon agricultural and weather data into charts, summaries, and inspectable evidence.

It keeps one primary product surface, the Streamlit UI, backed by one shared pipeline:

`parse -> validate -> fetch -> summarize -> visualize`

Its main job is to help a user investigate a question by returning useful visuals plus the underlying rows and metadata. For complex agronomic prompts, the Spring MVP is not trying to produce an authoritative final answer on its own. It is trying to give the user enough evidence to answer the question themselves.

## What It Supports

- Time series visualizations
- Statistical summaries
- Crop summaries by city or county
- Inspectable plotted rows and figure metadata
- Two data sources:
  - OpenET field and crop data from local GeoPackages
  - AgriMet weather data from local CSVs

SmartTap no longer includes AI follow-up generation, conversational spec patching, or comparison workflows.

## Quick Start

1. Create a virtual environment and install dependencies.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Make sure Ollama is available for natural-language parsing.

```bash
ollama pull gemma3:latest
ollama serve
```

3. Run the app.

```bash
./run_ui.sh
```

The UI starts at [http://localhost:8501](http://localhost:8501).

## CLI

The CLI is a thin wrapper around the same shared service used by the UI.

```bash
python smarttap.py "Show temperature in Corvallis for July 2024"
```

## Example Queries

```bash
Show temperature in Corvallis for July 2024
What is the average ETa in Hood River in 2024?
What crops are grown in Benton County?
Show precipitation in Pendleton in 2023
```

These examples should be read as requests for analytical views. The narrative text is supportive context, but the primary deliverable is the chart, plotted data, and figure metadata that help the user interpret the result.

The UI presents one deterministic explanation card alongside the chart plus a separate details section for metadata and the resolved request. Explanation text is generated from task-aware rules, not as a free-form LLM sidecar.

## Data Requirements

SmartTap expects these local files:

- `data/agrimet/*.csv` for AgriMet weather
- `data/field_points.gpkg`
- `data/preliminary_or_field_geopackage.gpkg`
- `data/CDL_Crop_Codes_Oregon.csv`

Optional:

- `AGRIMET_USE_API=1` to use the AgriMet API instead of local CSVs

## Project Shape

```text
smarttap_service.py        Shared application pipeline
smarttap_ui.py             Streamlit UI
smarttap.py                Thin CLI wrapper
core/data_fetcher.py       Local/API data access
core/location_crop_query.py OpenET crop and field queries
core/validation.py         Query and payload validation
core/visualizer.py         Chart rendering and Vega-Lite specs
llm/interpretation.py      Ollama-backed natural-language parsing
tests/                     Deterministic tests for the retained product surface
```

## Testing

Run the retained tests with:

```bash
python -m pytest -q tests/test_imports.py tests/test_visualizer.py tests/test_data_fetcher.py tests/test_service.py
```
