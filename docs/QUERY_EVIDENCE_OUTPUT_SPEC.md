# Query Evidence Output Spec

This document defines the current evidence package behavior for SmartTap.

## Product Position

SmartTap returns evidence packages, not authoritative agronomic conclusions.

A successful result should make the following explicit:

- the resolved query shape
- the dataset and location used
- the variables and date range that were actually plotted
- the validation state of the returned rows

## Supported Public Tasks

The retained user-facing tasks are:

- `visualize_timeseries`
- `statistical_summary`
- `summarize_crops`

## Confirmation and Clarification

Current workflow:

1. Parse the user prompt into an initial spec
2. Validate and normalize the spec
3. Ask clarification questions when required fields are still missing
4. Show a confirmation card before fetch/plot execution
5. Run fetch and visualization only after confirmation

## Evidence Package Shape

Successful results should produce:

- resolved query metadata
- a primary chart
- plotted data preview
- CSV and Vega artifacts
- deterministic validation output
- deterministic explanation text

## Artifact Destinations

### Runtime ad hoc outputs

Ad hoc runs write local outputs under:

`outputs/partner_queries/<case_id>/`

These outputs are runtime-only and ignored by git.

### Tracked handoff artifacts

Tracked handoff material lives in:

- `artifacts/qa/`
- `artifacts/examples/partner_queries/`

`scripts/export_qa_bundle.py` is the canonical way to regenerate the tracked QA bundle.

## Workbook Acceptance Set

The current acceptance source of truth is:

- `docs/query.xlsx`
- `tests/fixtures/acceptance_queries.json`

The workbook QA bundle in `artifacts/qa/` is a checked-in review handoff, not a runtime output location.

## Test Expectations

The retained suite should verify:

- parsing and validation behavior
- dataset fetch behavior
- explanation and chart generation
- QA bundle export behavior
- runtime evidence artifact paths

The baseline acceptance command is:

```bash
python -m pytest -q
```
