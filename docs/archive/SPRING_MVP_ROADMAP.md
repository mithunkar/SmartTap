# Spring MVP Roadmap

## Purpose

This document turns partner expectations and scattered project ideas into a single planning reference for the Spring term. It is meant to stay stable while implementation changes happen around it.

The companion document, `docs/SPRING_MVP_BACKLOG.md`, is the working checklist we will update as items move from idea to implementation.

## Spring-Term Goals

The Spring MVP should demonstrate a user-facing SmartTap workflow where:

- a user asks a question in natural language
- the system can request missing details when needed
- the system confirms the resolved analytical view it will produce
- the system returns an evidence package made up of charts, text, and inspectable data
- the user can inspect the plotted rows and figure metadata
- the user can use the returned visuals to answer a complex question themselves

This is aligned with the partner goals:

- test example queries with combined text and visual outputs
- compare those evidence packages against data-only results
- integrate visualization with the existing AgWaterTAP-style LLM + RAG chat flow
- support follow-up clarification for location and time range
- generate time-series, ranking, and comparative plots
- produce documentation and a final MVP demonstration

## Current Codebase Reality Check

SmartTap currently has a solid Python-first base, but it does not yet match the full partner vision.

### What exists now

- Python/Streamlit UI in `smarttap_ui.py`
- Shared pipeline in `smarttap_service.py`
- LLM-based query interpretation in `llm/interpretation.py`
- Validation, fetching, and chart generation in `core/`
- Support for:
  - time-series visualizations
  - statistical summaries
  - crop summaries by city or county
  - clarification prompts for incomplete requests
- output artifacts including:
  - PNG charts
  - Vega-Lite specs
  - validation reports
  - preview tables
- deterministic tests for the retained product surface

### What is not in the retained product surface today

- implemented comparison workflows as a supported task
- a React frontend
- a clearly defined adapter contract for adding future datasets with minimal code changes

### Important gaps already visible in the code

- The README explicitly says AI follow-up generation and comparison workflows were removed from the retained product surface.
- AgriMet support is partial for the partner's desired variables and station-selection behavior.
- Some docs describe architecture that is broader than the current implementation, so new planning work should stay grounded in the code that is actually present.
- The codebase is usable, but the extensibility story is not yet formalized enough for an easy handoff to a future team.
- Clarification is now present, but it still needs richer station selection, crop refinement, and final confirmation UX to fully match the partner vision.

## MVP Definition

The Spring MVP is complete when SmartTap can demonstrate conversations that produce:

- framing text that explains what the charts show
- confirmation of the resolved prompt/spec
- one chart or a coordinated set of charts
- plotted data rows the user can inspect
- figure variables/specs the user can inspect
- enough evidence for the user to infer the answer to the original question

For partner prompts like the ones in `docs/query.xlsx`, SmartTap should treat the spreadsheet as an evaluation and prompt-source artifact, not as a promise that the system will directly answer every prompt end to end. The goal is to choose chart outputs that make those questions answerable by the user.

For Spring, the MVP should stay on the current Python/Streamlit stack unless a backend/API seam is needed to reduce future React rework.

## Major Workstreams

### 1. Modular architecture and contracts

Goal: reduce spaghetti-code risk and make future additions low-friction.

This workstream should define:

- a canonical `QuerySpec` shape
- a canonical `VisualizationResult` shape
- dataset adapter boundaries
- where prompt templates live
- where variable mappings and synonyms live
- how a future team adds a dataset without editing the entire pipeline

### 2. Conversational clarification workflow

Goal: restore the ability to refine ambiguous or incomplete requests instead of failing fast.

This includes:

- asking follow-up questions for missing time range
- asking follow-up questions for missing or ambiguous location
- asking the user to pick a station when a city maps to multiple AgriMet stations
- refining crop filters and variable selection as needed
- storing the resolved query state across turns

### 3. Visualization integration in the chat experience

Goal: make the SmartTap output feel like one coherent evidence package.

This includes:

- combined text plus chart output
- prompt/spec confirmation in the UI
- one explanation card instead of duplicate summary blocks
- evidence-pattern routing so the system can choose the right chart package for the prompt class
- access to plotted rows
- access to variable and figure metadata
- support for multiple coordinated charts when one chart is not enough
- short deterministic framing text that explains why a chart was chosen
- reusable output payloads that can later support a React client

### 4. Data and evidence coverage

Goal: cover the most important partner prompt patterns with trustworthy evidence outputs.

Priority items include:

- stronger OpenET and AgriMet variable coverage
- `IRR_STATUS` handling for irrigation-focused queries
- better OpenET vs AgriMet routing for overlapping concepts such as precipitation
- reusable chart-selection and aggregation helpers for trends, totals, means, comparisons, rankings, and irrigation-focused summaries

### 5. Evaluation and documentation

Goal: make progress measurable and handoff-ready.

This includes:

- turning example partner queries into evidence-design acceptance scenarios
- maintaining `docs/QUERY_EVIDENCE_OUTPUT_SPEC.md` as the workbook-to-output acceptance map
- comparing text + visual outputs against data-only outputs
- documenting methods, limitations, challenges, and future improvements
- writing code documentation that explains how to extend the project

## Acceptance Prompt Coverage

The partner query table should be treated as an acceptance and evaluation source, not as a flat implementation checklist. For Spring, the most useful approach is to group those prompts into representative query classes and make sure each class has at least one passing workflow.

Each workflow should be judged by whether SmartTap returns an appropriate evidence package for the prompt class, not by whether the system automatically states the final answer in prose.

`docs/QUERY_EVIDENCE_OUTPUT_SPEC.md` is the implementation-ready mapping from workbook rows to expected evidence outputs.

### Class A: Single-variable OpenET trend queries

Examples:

- farmland area changes over time
- irrigation efficiency trend
- ETa trend
- precipitation trend
- applied water trend

Needed behaviors:

- location resolution
- time-range handling
- crop filtering when present
- monthly or yearly aggregation
- a chart that makes the trend visible enough for the user to interpret

### Class B: Single-variable AgriMet trend queries

Examples:

- temperature near a city
- daily precipitation around a city
- humidity or wind around a city

Needed behaviors:

- city-to-station resolution
- station selection when ambiguous
- time-range handling
- daily aggregation with optional rollups
- a chart and metadata that make station choice and temporal pattern clear

### Class C: Crop summary and ranking queries

Examples:

- what crops were most common
- which crops occupied the largest area

Needed behaviors:

- crop grouping
- area/count ranking
- clear location and year handling
- ranking-oriented charts or tables that let the user see the dominant crops directly

### Class D: Irrigation-focused queries

Examples:

- irrigated share trend
- irrigated field counts
- irrigation status + water use relationship

Needed behaviors:

- explicit `IRR_STATUS` filtering logic
- explainable treatment of non-irrigated records
- chart annotations or metadata that make the irrigation filter transparent

### Class E: Multi-variable same-location comparisons

Examples:

- water applied vs ETa
- PPT vs effective precipitation
- ETa vs NIWR vs AW
- PEN_ET vs AVG_TMP

Needed behaviors:

- shared time axis
- chart selection logic
- metadata that explains the comparison
- support for multiple coordinated charts when overloading one figure would hurt readability

### Class F: Cross-dataset comparisons

Examples:

- OpenET ETa + AgriMet PEN_ET + OpenET PPT

Needed behaviors:

- cross-dataset query planning
- aligned time ranges
- honest communication about differences in source, spatial resolution, and units
- evidence outputs that help the user reason across datasets without hiding those differences

## Phased Roadmap

### Phase 1: Clean internal contracts

- define canonical query/result shapes
- define dataset adapter boundaries
- move mappings and prompt dependencies into clearer configuration locations
- document how the pipeline is supposed to work

### Phase 2: Restore conversational refinement

- add clarification rules for missing time range, location, station, and crop filter
- support continuing follow-up questions until the plotting request is complete
- keep resolved query state in session

### Phase 3: Improve output transparency

- show prompt/spec confirmation
- show plotted rows
- show figure variables and metadata
- make output payload reusable across UI layers

### Phase 4: Expand evidence coverage

- implement priority evidence-output patterns for partner prompt classes
- strengthen AgriMet support and city-to-station handling
- add irrigation-aware filtering

### Phase 5: Evaluate and document

- convert representative partner prompts into acceptance tests
- compare data-only and text + visual output modes
- write final code documentation and Spring report material

## Post-MVP Items

These are important, but they should not block the Spring MVP unless they are required to reduce obvious future rework.

- React frontend migration
- internal API/service layer for frontend independence
- support for more datasets such as PRISM, SMAP, and CDL-derived layers
- richer comparison workflows
- broader evaluation coverage across more partner prompts

## Working Assumptions

- The roadmap document is the reference document.
- The backlog document is the execution document.
- Spring MVP work should focus on one backlog item at a time.
- React is a post-MVP follow-on unless backend seams need to be introduced sooner.
- “Combined text and visual outputs” means the response should contain both narrative and figure output for supported query flows.
