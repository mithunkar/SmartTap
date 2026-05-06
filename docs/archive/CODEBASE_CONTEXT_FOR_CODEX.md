# SmartTap Codebase Context for Codex

## 1. Project Overview

### What this project does
SmartTap is a Python application that lets users ask natural-language questions about Oregon agricultural and weather data, then returns charts, summaries, and inspectable evidence.

### Main problem it solves
It reduces manual GIS/data-engineering effort by translating plain-English analytical questions into executable data queries over large local datasets (OpenET field data and AgriMet weather data), then packaging the results so users can investigate those questions through visuals and supporting data.

### Key features and functionality
- Natural-language query parsing into a structured task specification.
- Evidence-oriented query handling built on a small task set plus evidence-pattern routing.
- Two data domains:
  - OpenET-like field/crop data from GeoPackage files
  - AgriMet weather station data from local CSVs or optional API mode
- Chart generation as PNG plus Vega-Lite JSON, including optional companion charts.
- Validation reports, deterministic explanation text, and inspectable plotting context.
- Follow-up question generation and session refinement in the Streamlit UI.

---

## 2. Architecture & Tech Stack

### Technologies, frameworks, and libraries
- Language: Python
- UI: Streamlit (`smarttap_ui.py`)
- Data processing: pandas
- Charting: matplotlib + generated Vega-Lite specs
- LLM integration: Ollama Python client (`ollama`) with local model (default references Gemma variants)
- HTTP client: httpx (AgriMet API integration)
- Config parsing: pyyaml
- Image handling: pillow (UI path)
- Storage/data access:
  - CSV files (`data/agrimet/*.csv`)
  - GeoPackage (SQLite-backed) files in `data/`

### High-level system design
- Frontend/UI:
  - Streamlit chat-style app (`smarttap_ui.py`) with handler registry pattern.
- Backend/application logic:
  - In-process Python modules in `core/` and `llm/`.
- APIs:
  - No internal HTTP API server currently implemented.
  - Optional outbound AgriMet API fetch path exists in `core/agrimet_api.py`.
- Database/data layer:
  - Local files (GeoPackage + CSV) as primary data source.

### How components interact
1. User enters query in Streamlit UI or CLI.
2. `llm/interpretation.py` converts text to a spec dictionary.
3. Spec is validated/repaired (`core/validation.py`) and routed into an evidence pattern (`core/evidence_router.py`).
4. Data is fetched (`core/data_fetcher.py`, sometimes via `core/location_crop_query.py`).
5. Data payload is validated (`validate_payload`).
6. Visualization artifacts are generated (`core/visualizer.py`).
7. Deterministic explanation text and clarification prompts are produced before the UI renders the result.
8. Streamlit displays chart/data/follow-ups and stores session context.

---

## 3. Codebase Structure

### Top-level organization
- `smarttap_ui.py`: primary Streamlit web UI and query handler registry.
- `smarttap.py`: CLI-oriented orchestration and pipeline execution.
- `core/`: deterministic data/query/validation/visualization modules.
- `llm/`: natural-language parsing, follow-ups, and session patch logic.
- `data/`: local datasets and keyword dictionaries.
- `prompts/`: externalized prompt templates.
- `docs/`: architecture, testing, handler, and extension documentation.
- `tests/`: unit/integration/evaluation scripts and fixtures.
- `outputs/`: generated charts and validation artifacts.
- `scripts/`: helper utilities for dataset prep/fetch.

### Purpose of each major module directory
- `core/`
  - `data_fetcher.py`: unified data retrieval for OpenET and AgriMet paths.
  - `evidence_router.py`: evidence-pattern routing and chart-package selection.
  - `location_crop_query.py`: city/county to field-ID mapping, crop filtering, and variable extraction from GeoPackage.
  - `visualizer.py`: chart payload shaping, chart-type/view choice, PNG + Vega spec generation.
  - `validation.py`: spec and payload validation/fixing.
  - `query_contract.py`: normalized contract generation from parsed query specs.
  - `analysis_router.py`: deterministic rule-based mapping to analysis function identifiers.
  - `explanation.py`: task-aware deterministic explanation builders for result framing text.
  - `config_loader.py`: YAML config access with singleton loader.
- `llm/`
  - `interpretation.py`: NL query to task spec.
  - `followups.py`: follow-up question generation.
  - `session_update.py`: follow-up-to-patch generation and patch apply logic.
  - `keyword_matcher.py`: variable/crop keyword matching support.
  - `config.py`: model configuration defaults.

---

## 4. Key Components & Logic

### Important classes/functions/modules
- `smarttap_ui.py`
  - `QueryHandler` base interface and `@register_handler` registry.
  - concrete handlers for crop summaries, time-series, statistical summaries, comparisons.
  - `process_query_ui(...)` orchestration through handler selection.
- `smarttap.py`
  - `run_pipeline(query, spec, base, chart_dir, validation_dir)` is the central pipeline entry used by CLI-style flow.
- `llm/interpretation.py`
  - `get_task_specification(user_query)` parses NL into structured JSON-like dict.
- `core/data_fetcher.py`
  - `fetch_data(spec)` returns normalized payload shape consumed by visualizer/validation.
- `core/location_crop_query.py`
  - location and crop mapping logic over GeoPackage tables.
- `core/visualizer.py`
  - `payload_to_df`, `choose_view`, `png_bytes`, `vega_spec`, `create_crop_bar_chart`.
- `core/validation.py`
  - `validate_and_fix_spec(...)` and `validate_payload(...)`.
- `core/evidence_router.py`
  - `route_evidence_pattern(...)` for evidence-intent classification and package selection.
- `core/explanation.py`
  - `build_result_explanation(...)` for canonical explanation text.
- `llm/session_update.py`
  - `spec_patch_from_followup(...)`, `apply_patch(...)` for multi-turn refinement.
- `core/analysis_router.py`
  - `route_analysis_function(contract)` for deterministic function labels.

### Core workflows

#### Workflow A: Streamlit user query flow
1. User submits chat prompt.
2. Query parsed into spec.
3. Handler chosen by `can_handle(spec)` registry scan.
4. Handler fetches data and builds chart.
5. Validation + evidence-pattern routing + deterministic explanation/details + clarification prompts returned to UI.
6. Session state updated for subsequent refinements.

#### Workflow B: CLI/pipeline flow
1. Query/spec passed to `run_pipeline`.
2. `fetch_data` -> `validate_payload` -> `choose_view` -> `png_bytes` + `vega_spec`.
3. Output files written into `outputs/charts` and `outputs/validation`.
4. Follow-up suggestions generated and persisted.

#### Workflow C: Location/crop query flow (OpenET path)
1. Resolve city/county to relevant `OPENET_ID` field set.
2. Pull crop and variable columns from GeoPackage tables.
3. Optional crop filtering.
4. Aggregate and reshape to timeseries/summary records.
5. Return payload for visualization.

---

## 5. Current State of the Codebase

### Completed features
- Modular handler-registry architecture in Streamlit UI (`smarttap_ui.py`).
- External prompt templates in `prompts/` and prompt-loading integration in `llm/` modules.
- Core query/data/visualization/validation pipeline functional for both UI and CLI usage.
- Deterministic routing, evidence-package selection, and explanation infrastructure in `core/`.
- Testing framework and model-comparison/evaluation scripts under `tests/` and `evaluation_results/`.

### Partially implemented or unfinished features
- Phase-2 items called out in docs remain pending (for example IRR-status filtering and fuller field-selection UX).
- Location metadata return infrastructure exists in query logic, but complete interactive UI utilization is not fully documented as complete.
- Planned extensibility via YAML config is partially inconsistent with current repository state (see issues below).

### Known issues, technical debt, inconsistencies
- Config mismatch:
  - `core/config_loader.py` expects YAML files in `config/`, but current `config/` folder is empty.
  - Loader has fallback behavior (warn and continue with empty config), which can mask configuration defects.
- Documentation mismatch:
  - Some docs describe created config files that are not currently present in workspace.
- LLM parsing quality variability:
  - `evaluation_results/model_comparison_20260309_000803.json` shows low accuracy for tested models in that run, with many errors caused by normalization/schema mismatches (for example case sensitivity and missing expected fields).
- Potential contract seam risk:
  - Deterministic router expects normalized contract fields; parsed specs and downstream usage rely on adapters/normalization consistency.
- Project currently lacks an internal HTTP API layer, which limits direct integration from external frontends/services without wrapping.

### Explicit unclear or missing information
- Required Python version is not explicitly pinned in README/requirements metadata.
- Current authoritative source for `config/*.yaml` is unclear (docs claim existence; repository currently shows empty config directory).
- No single source of truth for model recommendation despite multiple evaluation artifacts.

---

## 6. Setup & Running the Project

### Installation steps (local)
1. Create and activate a Python virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Ensure Ollama is installed and model is available.
4. Start Ollama server:
   - `ollama serve`

### Run commands
- Web UI (recommended):
  - `./run_ui.sh`
- CLI:
  - `python smarttap.py "Show temperature in Corvallis for July 2024"`

### Environment variables
- `AGRIMET_USE_API`
  - `1` to prefer live AgriMet API path, otherwise local CSV path.
- `OLLAMA_HOST`
  - Ollama endpoint (defaults to localhost in code paths/docs).
- `SMARTTAP_MODEL`
  - Model override for LLM tasks.

### Notes
- `run_ui.sh` auto-creates `venv` if missing, installs minimal UI packages, checks Ollama process, and starts Streamlit.
- Large local data files are required for full OpenET functionality (GeoPackage files in `data/`).

---

## 7. Development Guidelines

### Coding patterns used
- Handler registry pattern in UI for extensible query-type handling.
- Functional pipeline orchestration (`run_pipeline`) for deterministic processing steps.
- Prompt externalization (`prompts/*.txt`) to reduce hardcoded prompt logic.
- Config-loader singleton for centralized settings access.
- Explicit validation stage before visualization and response generation.

### Conventions/standards observed
- Python module separation by concern (`core/` vs `llm/`).
- Tests organized by concern (`test_data_fetcher`, `test_pipeline`, `test_llm_*`).
- Output artifacts written to timestamped files under `outputs/`.
- Documentation-driven extension guides in `docs/`.

### Practical developer guidance
- When extending query behavior, add/modify handler classes in `smarttap_ui.py` and keep `can_handle` logic explicit.
- Preserve payload/spec contract compatibility between parser, fetcher, validator, visualizer, and router.
- If adding config-driven behavior, resolve current config-file inconsistencies first.

---

## 8. Project Goals & Roadmap

### Intended final product (as implied by code/docs)
A robust natural-language agronomic analytics assistant with:
- reliable query interpretation,
- deterministic routing and summaries,
- multi-turn conversational refinement,
- transparent chart/data outputs that function as user-facing evidence,
- and modular extensibility to new datasets/query types.

For Spring MVP planning, the intended outcome is not an authoritative automated answer to every complex question in `docs/query.xlsx`. The intended outcome is a trustworthy evidence package of charts, plotted rows, specs, and framing text that helps the user answer those questions themselves.

### Features still to be built or stabilized
- Complete Phase-2 features referenced in docs (for example IRR filtering and richer field-level selection UX).
- Stronger parser normalization and schema consistency to improve evaluation accuracy.
- Consistent configuration packaging (ensuring YAML config artifacts and runtime expectations match).
- Potential API service layer for external app/frontend integration.

### Suggested next steps for development
1. Resolve config source-of-truth: restore or regenerate `config/*.yaml`, then fail fast if required config is missing.
2. Define and enforce a canonical query-spec/contract schema (including normalization rules such as location casing and required fields).
3. Add regression tests focused on prompt/spec contract stability and deterministic router expectations.
4. Establish model quality gates (minimum parsing accuracy thresholds) and automate model comparison in CI.
5. Introduce a minimal HTTP API wrapper (for example FastAPI) around parse/fetch/visualize/followup endpoints to support integration with non-Streamlit clients.

---

## Quick Orientation Index for Codex
- UI entry point: `smarttap_ui.py`
- CLI/pipeline entry point: `smarttap.py`
- Query parsing: `llm/interpretation.py`
- Session refinement: `llm/session_update.py`
- Data fetch: `core/data_fetcher.py`
- Spatial crop/location logic: `core/location_crop_query.py`
- Validation: `core/validation.py`
- Visualization: `core/visualizer.py`
- Deterministic routing: `core/query_contract.py`, `core/analysis_router.py`
- Deterministic explanation text: `core/explanation.py`
- Setup docs: `README.md`, `docs/TESTING.md`
- Implementation-status docs: `docs/IMPLEMENTATION_SUMMARY.md`, `docs/UI_REFACTORING_SUMMARY.md`
