# Spring MVP Backlog

## How To Use This Backlog

This is the working execution document for the Spring MVP. The roadmap in `docs/SPRING_MVP_ROADMAP.md` explains the broader goals; this file breaks those goals into concrete items we can tackle one at a time.

Status markers:

- `[NOW]` highest-priority item for the current implementation pass
- `[NEXT]` important follow-on work after current priorities
- `[LATER]` valuable but not required for the Spring MVP
- `[DONE]` completed items

Each item includes:

- goal
- why it matters
- concrete deliverable
- dependencies
- acceptance check

## Next Up

`[NOW-3]` Show plotted rows and figure metadata/specs in the UI.

This is the next implementation item now that the clarification backbone is working and the UI already exposes the evolving resolved request. It is also the core building block for the evidence-package framing of the MVP.

## Now

### [NOW-2] Reintroduce conversational clarification for incomplete requests

Goal:
Allow SmartTap to ask follow-up questions when a plot request is missing required details.

Why it matters:
The partner MVP depends on the system refining ambiguous requests instead of just failing or guessing badly.

Concrete deliverable:

- clarification policy for missing location, station, time range, variable, and crop filter
- session state updates that preserve the resolved request across turns
- user-visible confirmation of the final resolved request before plotting

Dependencies:

- `[NOW-1]` contract definition

Acceptance check:

- incomplete prompts trigger a follow-up request instead of a hard failure
- the conversation can continue until the plot spec is complete
- the UI shows the partially resolved request while clarification is in progress

### [NOW-3] Show plotted rows and figure metadata/specs in the UI

Goal:
Make SmartTap outputs transparent and useful as analytical evidence.

Why it matters:
The partner explicitly wants users to see the rows being plotted and the variables/specs for the figure, and the instructor feedback makes those inspectable outputs central to how users answer complex prompts.

Concrete deliverable:

- plotted data table in the UI
- figure metadata block
- clear display of variables, location/station, date range, aggregation, and chart type
- access to the Vega-Lite spec or equivalent figure spec
- short framing text that explains what the chart helps the user determine

Dependencies:

- stable result payload from `[NOW-1]`

Acceptance check:

- a supported query returns figure + framing text + inspectable rows + inspectable metadata/spec
- the rows/spec/metadata are positioned as part of the user-facing evidence package, not just debugging output

### [NOW-4] Improve AgriMet city-to-station handling

Goal:
Make city-based AgriMet queries more accurate and transparent.

Why it matters:
The partner wants city requests to show all stations, and the current logic is still limited.

Concrete deliverable:

- city lookup that returns candidate stations
- station selection step when multiple stations are relevant
- improved station metadata surfaced to the user

Dependencies:

- `[NOW-2]` clarification workflow

Acceptance check:

- when a city maps to multiple plausible stations, the system asks the user to choose instead of silently picking one

### [NOW-5] Add `IRR_STATUS` handling for irrigation-focused analysis

Goal:
Make irrigation-related OpenET queries treat irrigation status explicitly.

Why it matters:
Partner notes call out the irrigation indicator and the need to ignore non-irrigated records in the right contexts.

Concrete deliverable:

- explicit rule for when `IRR_STATUS == 0` records are excluded
- tests for irrigation-focused query behavior
- documentation explaining the rule

Dependencies:

- `[NOW-1]` contract definition
- query-routing rules for irrigation-focused prompts

Acceptance check:

- supported irrigation-focused prompts apply the filtering rule consistently and transparently

## Next

### [NEXT-1] Convert partner prompt examples into an MVP acceptance set

Goal:
Turn the long partner prompt table into a compact but meaningful evidence-output acceptance suite.

Why it matters:
This creates a stable definition of “working MVP” and supports evaluation.

Concrete deliverable:

- `docs/QUERY_EVIDENCE_OUTPUT_SPEC.md` as the source-of-truth acceptance doc
- representative prompts grouped by query class
- expected resolved specs
- recommended chart or chart-set patterns for each class
- expected output mode and validation notes

Dependencies:

- `[NOW-1]` contract definition
- `[NOW-2]` clarification behavior

Acceptance check:

- the team can point to a concrete set of example prompts that define MVP readiness
- each prompt class has a documented evidence pattern that would let a user answer the question from the returned visuals and tables

### [NEXT-2] Strengthen analysis function coverage

Goal:
Support the core evidence patterns represented in partner examples.

Why it matters:
Many partner prompts depend on more than simple plotting, but the Spring goal is to return the right evidence package rather than claim a final direct answer.

Concrete deliverable:

- helper functions for trends, totals, rankings, shares, and variable comparisons
- chart recommendation and chart-combination rules for those evidence patterns
- explicit mapping from query class to evidence-output pattern
- class-based implementation tickets derived from `docs/QUERY_EVIDENCE_OUTPUT_SPEC.md`

Dependencies:

- `[NEXT-1]` acceptance query set

Acceptance check:

- representative prompt classes produce sensible outputs without one-off logic spread across the codebase
- for each supported class, the user can reasonably infer the answer from the returned charts and tables

### [NEXT-3] Document dataset-extension and prompt-edit workflows

Goal:
Make handoff to a future team straightforward.

Why it matters:
Modularity only matters if another team can understand and use it.

Concrete deliverable:

- step-by-step dataset extension workflow
- prompt-edit workflow
- architecture note explaining ownership of major modules

Dependencies:

- `[NOW-1]` contract definition

Acceptance check:

- a new contributor can identify where to add a dataset, a variable mapping, or a prompt change without tracing the whole repo

## Later

### [LATER-1] Prepare a stable API boundary for frontend independence

Goal:
Make it easier to swap the frontend without rewriting core logic.

Why it matters:
The partner mentioned a React port, but doing that too early could slow MVP delivery.

Concrete deliverable:

- stable request/response schema
- service/API boundary around the shared pipeline

Dependencies:

- `[NOW-1]` contract definition
- `[NOW-3]` stable output payload

Acceptance check:

- the frontend can be changed later without redesigning the core processing flow

### [LATER-2] Port the UI to React

Goal:
Move the user-facing interface to React once the workflow is stable.

Why it matters:
This may improve long-term maintainability and integration options, but it should not destabilize the Spring MVP.

Concrete deliverable:

- React frontend consuming a stable SmartTap result payload

Dependencies:

- `[LATER-1]` API boundary

Acceptance check:

- the React UI can reproduce the MVP workflow without changing backend behavior

### [LATER-3] Add new datasets

Goal:
Extend SmartTap beyond the current OpenET and AgriMet data sources.

Why it matters:
The partner already identified likely future datasets such as PRISM, SMAP, and USDA CDL-related sources.

Concrete deliverable:

- at least one new dataset integrated through the adapter contract

Dependencies:

- `[NOW-1]` dataset adapter contract
- `[NEXT-3]` extension documentation

Acceptance check:

- a new dataset can be added with localized changes instead of repo-wide edits

## Done

### [DONE-2] Reintroduce conversational clarification for incomplete requests

Completed work:

- clarification is now a first-class service response path
- missing location, time range, variable, and unsupported local AgriMet station cases trigger follow-up prompts
- parser-supplied locations and time ranges are dropped when the user did not actually mention them
- pending specs are patched across clarification turns instead of concatenating the whole conversation back into one prompt
- user-confirmed fields persist across later clarification turns
- the Streamlit UI shows the evolving resolved request while clarification is in progress

Why this is done:

- incomplete requests no longer silently guess required fields
- the conversation can refine a query across multiple turns without losing already confirmed information

### [DONE-1] Define modular architecture and internal contracts

Completed work:

- canonical `QuerySpec` and `VisualizationResult` added in `core/contracts.py`
- shared result shaping adopted in `smarttap_service.py`
- dataset adapter boundary documented and lightly scaffolded in `core/data_fetcher.py`
- architecture contract documented in `docs/ARCHITECTURE_CONTRACTS.md`
- shared variable aliases and labels centralized in `core/variable_registry.py`

Why this is done:

- future tasks now have one source of truth for query shape, result shape, dataset adapter intent, and mapping ownership
