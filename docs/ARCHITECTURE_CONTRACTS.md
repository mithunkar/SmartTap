# Architecture Contracts

This document is the current source of truth for how SmartTap is organized.

## Pipeline

SmartTap’s retained pipeline is:

`query text -> parse -> validate -> fetch -> validate payload -> visualize -> explain`

Module ownership:

- `llm/interpretation.py`: natural-language parsing into an initial spec
- `core/validation.py`: normalization, defaulting, clarification, and repair
- `core/evidence_router.py`: evidence-pattern routing metadata
- `core/data_fetcher.py`: dataset adapter boundary and fetch orchestration
- `core/location_crop_query.py`: OpenET city/county field and crop resolution
- `core/visualizer.py`: chart and table artifact generation
- `core/explanation.py`: deterministic explanation text
- `smarttap_service.py`: end-to-end orchestration and final result packaging
- `core/contracts.py`: canonical query/result contracts

## Public Contracts

### Query contract

The canonical resolved query contract is `QuerySpec` in `core/contracts.py`.

Core fields used across the retained surface:

- `task`
- `dataset`
- `location`
- `location_type`
- `variables`
- `start_date`
- `end_date`
- `interval`
- `chart_type`

Common optional fields:

- `display_location`
- `station_id`
- `station_title`
- `aggregation`
- `crop_filter`
- `year`
- `evidence_pattern`
- `compare_by`
- `source_datasets`
- `openet_geo`

Ownership rules:

- parsing may leave fields missing
- validation owns defaulting and normalization
- fetchers consume resolved specs; they should not invent new user-facing spec fields

### Result contract

The canonical service output is `VisualizationResult` in `core/contracts.py`.

Successful results should include:

- `success`
- `spec`
- `summary`
- `explanation`
- `data_preview`
- `data`
- `chart_bytes`
- `vega_spec`
- `secondary_views`
- `files`
- `validation_report`

Clarification and confirmation flows should keep the same outer result shape and surface their next-step prompts explicitly.

## Filesystem Contracts

### Tracked source-of-truth assets

- `reference/`: small static assets used by runtime code and handoff docs
- `docs/`: current onboarding and architecture docs
- `artifacts/qa/`: tracked workbook QA bundle
- `artifacts/examples/partner_queries/`: tracked sample evidence runs

### Local-only data

- `data/agrimet/*.csv`
- `data/openet/field_index.parquet`
- `data/openet/annual/*.parquet`
- `data/openet/monthly/*/*.parquet`
- `data/field_points.gpkg`
- `data/preliminary_or_field_geopackage.gpkg`
- `data/archive/preliminary_or_field_geopackage.7z`

### Runtime-generated outputs

- `outputs/`: ad hoc local run outputs only
- `outputs/partner_queries/<case_id>/`: runtime evidence package output path

The runtime code should never write ad hoc outputs into tracked `artifacts/`.

## Dataset Boundary

The service layer owns orchestration. Dataset adapters own dataset-specific fetch behavior.

Current active data-loading behavior:

- OpenET location queries use normalized parquet runtime artifacts in `data/openet/`
- AgriMet uses local CSVs when available and the API fallback only when required by variable/support constraints
- legacy combined OpenET CSV loaders remain explicit non-location paths only

## Maintenance Rules

- add new tracked reference/config assets under `reference/`, not `data/`
- keep heavy datasets out of git
- archive historical docs under `docs/archive/`
- keep legacy scripts behind the `scripts/archive/` boundary
- update tests whenever a filesystem contract changes
