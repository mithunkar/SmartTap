# Repo Handoff

This file explains what belongs in GitHub, what stays local, and where to look first when taking over SmartTap.

## Source of Truth

GitHub is the source of truth for:

- runtime code
- current docs
- tests
- small static reference assets in `reference/`
- tracked handoff artifacts in `artifacts/`

Teams or other shared storage should only be used for files that are too large or unsuitable for git.

## Directory Guide

- `core/`, `llm/`, `smarttap_service.py`, `smarttap_ui.py`, `smarttap.py`
  - active runtime surface
- `reference/`
  - tracked small CSV/JSON/HTML/DOCX assets used by code and handoff docs
- `data/`
  - local-only heavy datasets and acquisition notes
- `artifacts/qa/`
  - tracked workbook QA export bundle
- `artifacts/examples/partner_queries/`
  - tracked example evidence runs
- `docs/`
  - current docs
- `docs/archive/`
  - historical or legacy docs retained for reference
- `scripts/`
  - active utilities
- `scripts/archive/`
  - legacy utilities outside the active runtime path
- `outputs/`
  - ignored local runtime outputs

## Required Local Data

See [data/README.md](/Users/mithunkarthikeyan/Desktop/Projects/SmartTap/data/README.md) for setup details.

At minimum, a full OpenET-enabled local run expects:

- `data/field_points.gpkg`
- `data/preliminary_or_field_geopackage.gpkg`
- `data/agrimet/*.csv`

## Reference Assets Todd Asked About

These are now tracked under `reference/`:

- `agrimet_stations_full_metadata.csv`
- `CDL_Crop_Codes_Oregon.csv`
- `openet_variable_keywords.json`
- `crop_name_keywords.json`

OpenET reference docs are also kept there when they are small enough to live in git.

## Artifacts

### Tracked artifacts

- `artifacts/qa/`: canonical workbook QA bundle
- `artifacts/examples/partner_queries/`: canonical example evidence runs

### Ignored runtime artifacts

- `outputs/charts/`
- `outputs/validation/`
- `outputs/partner_queries/`

Ad hoc runs should never write directly into tracked `artifacts/`.

## Tests

Primary command:

```bash
python -m pytest -q
```

Wrapper:

```bash
python tests/run_tests.py
```
