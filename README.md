# SmartTap

SmartTap turns plain-English questions about Oregon agricultural and weather data into charts, summaries, and inspectable evidence.

The retained product surface is one shared pipeline used by the Streamlit UI and CLI:

`parse -> validate -> fetch -> visualize -> explain`

SmartTap is an evidence system, not a final-answer engine. Its job is to return the right data, chart, and metadata package so the next reviewer can verify what the query actually shows.

## Supported Surface

- Time-series evidence views
- Statistical summaries
- Crop ranking and crop-distribution summaries
- Coordinated OpenET + AgriMet evidence packages
- Deterministic confirmation, clarification, validation, and explanation flows

Data sources:

- OpenET field and crop data from local GeoPackages
- AgriMet weather data from local CSVs, with optional API fallback for unsupported local variables

## Repo Layout

- `core/`, `llm/`, `smarttap_service.py`, `smarttap_ui.py`, `smarttap.py`: runtime code
- `reference/`: tracked small reference assets used by code and handoff docs
- `data/`: local-only heavy datasets and acquisition notes
- `artifacts/qa/`: tracked workbook QA bundle
- `artifacts/examples/partner_queries/`: tracked sample evidence runs
- `docs/`: current docs for onboarding, architecture, and handoff
- `docs/archive/`: historical planning and legacy reference docs
- `scripts/`: active utilities
- `scripts/archive/`: legacy utilities kept for reference only
- `tests/`: retained automated test suite

More detail is in [docs/REPO_HANDOFF.md](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/docs/REPO_HANDOFF.md).

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

3. Download the required local data into `data/`.

See [data/README.md](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/data/README.md).

4. Run the UI.

```bash
./run_ui.sh
```

The UI starts at [http://localhost:8501](http://localhost:8501).

## CLI

```bash
python smarttap.py "Show temperature in Corvallis for July 2024"
```

## Data Requirements

Tracked reference assets now live in `reference/`:

- `reference/agrimet_stations_full_metadata.csv`
- `reference/CDL_Crop_Codes_Oregon.csv`
- `reference/openet_variable_keywords.json`
- `reference/crop_name_keywords.json`

Required local data lives in `data/`:

- `data/agrimet/*.csv`
- `data/field_points.gpkg`
- `data/preliminary_or_field_geopackage.gpkg`

Optional:

- `AGRIMET_USE_API=1` to prefer the AgriMet API when local CSV coverage is insufficient
- `data/openet/field_combined_long.csv` and `data/openet/huc_combined_long.csv` only for legacy explicit non-location field/HUC fetch modes

## OpenET Note

The current statewide location-query path is GeoPackage-backed.

- City/county OpenET queries route through `core/location_crop_query.py`
- That path depends on `data/field_points.gpkg` and `data/preliminary_or_field_geopackage.gpkg`
- Archived CSV conversion scripts are not part of the active runtime path for location-based chat queries

## Testing

Run the retained suite with:

```bash
python -m pytest -q
```

The lightweight wrapper below runs the same suite:

```bash
python tests/run_tests.py
```

## Handoff Docs

- [docs/REPO_HANDOFF.md](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/docs/REPO_HANDOFF.md)
- [docs/ARCHITECTURE_CONTRACTS.md](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/docs/ARCHITECTURE_CONTRACTS.md)
- [docs/QUERY_EVIDENCE_OUTPUT_SPEC.md](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/docs/QUERY_EVIDENCE_OUTPUT_SPEC.md)
