from __future__ import annotations

import io
import json
from html import escape
from datetime import date, datetime

import streamlit as st
from PIL import Image

from core.variable_registry import variable_label, variables_for_dataset
from smarttap_service import apply_confirmation_edit, confirm_query, process_followup_reply, process_query


CONFIRMATION_EDIT_FIELDS = ["crop", "location", "time_range", "metric"]
CONFIRMATION_EDIT_LABELS = {
    "crop": "Crop",
    "location": "Location",
    "time_range": "Time Range",
    "metric": "Metric",
}


def _state_defaults() -> dict:
    return {
        "messages": [],
        "current_chart": None,
        "current_data": None,
        "current_details": None,
        "current_spec": None,
        "current_vega_spec": None,
        "current_files": None,
        "current_explanation": None,
        "current_secondary_views": None,
        "pending_spec": None,
        "confirmation_spec": None,
        "original_query": None,
        "followup_mode": None,
        "confirmation_editor_open": False,
        "confirmation_edit_field": None,
        "confirmation_edit_text": "",
        "confirmation_edit_start_date": None,
        "confirmation_edit_end_date": None,
        "confirmation_edit_metric": None,
    }


def _metric_options() -> list[str]:
    seen = set()
    options: list[str] = []
    for dataset in ["agrimet", "openet"]:
        for metadata in variables_for_dataset(dataset):
            if metadata.code not in seen:
                options.append(metadata.code)
                seen.add(metadata.code)
    return options


def _metric_option_label(code: str) -> str:
    return f"{variable_label(code)} [{code}]"


def _parse_spec_date(value) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _default_edit_dates(spec: dict) -> tuple[date, date]:
    start = _parse_spec_date(spec.get("start_date"))
    end = _parse_spec_date(spec.get("end_date"))
    if start and end:
        return start, end

    year = spec.get("year")
    try:
        year_value = int(year) if year is not None else datetime.now().year
    except (TypeError, ValueError):
        year_value = datetime.now().year
    return date(year_value, 1, 1), date(year_value, 12, 31)


def _seed_confirmation_editor_inputs(state: dict, spec: dict, field: str) -> None:
    selected_field = field if field in CONFIRMATION_EDIT_FIELDS else "crop"
    state["confirmation_edit_field"] = selected_field
    if selected_field == "crop":
        state["confirmation_edit_text"] = str(spec.get("crop_filter") or "")
    elif selected_field == "location":
        state["confirmation_edit_text"] = str(spec.get("display_location") or spec.get("location") or "")
    elif selected_field == "time_range":
        start_date, end_date = _default_edit_dates(spec)
        state["confirmation_edit_start_date"] = start_date
        state["confirmation_edit_end_date"] = end_date
    elif selected_field == "metric":
        metric_options = _metric_options()
        current_variable = next(iter(spec.get("variables") or []), "")
        if current_variable and current_variable not in metric_options:
            metric_options = [current_variable, *metric_options]
        state["confirmation_edit_metric"] = current_variable or (metric_options[0] if metric_options else "")


def _open_confirmation_editor(state: dict) -> None:
    if state.get("confirmation_spec") is None or not state.get("original_query"):
        return
    state["confirmation_editor_open"] = True
    _seed_confirmation_editor_inputs(state, state["confirmation_spec"], state.get("confirmation_edit_field") or "crop")


def _reset_confirmation_editor_inputs(state: dict) -> None:
    state["confirmation_editor_open"] = False
    state["confirmation_edit_field"] = None
    state["confirmation_edit_text"] = ""
    state["confirmation_edit_start_date"] = None
    state["confirmation_edit_end_date"] = None
    state["confirmation_edit_metric"] = None


def _close_confirmation_editor(state: dict) -> None:
    state["confirmation_editor_open"] = False
    state["confirmation_edit_field"] = None


def _next_query_action(
    query: str,
    *,
    followup_mode: str | None,
    pending_spec: dict | None,
    original_query: str | None,
) -> str:
    del query
    if followup_mode == "clarification" and pending_spec is not None and original_query:
        return "followup"
    return "new_query"


def _clear_query_context(state: dict) -> None:
    state["pending_spec"] = None
    state["confirmation_spec"] = None
    state["original_query"] = None
    state["followup_mode"] = None
    _reset_confirmation_editor_inputs(state)


def _display_spec(spec: dict) -> dict:
    hidden_keys = {
        "notes",
        "confirmed_fields",
        "confirmation_status",
        "openet_geo",
        "openet_id",
        "huc8_code",
        "secondary_variables",
        "chart_package",
        "source_datasets",
        "display_location",
    }
    display = {}
    for key, value in (spec or {}).items():
        if key in hidden_keys:
            continue
        if value in (None, "", [], {}):
            continue
        display[key] = value
    return display


def _format_label(key: str) -> str:
    return key.replace("_", " ").title()


def _format_value(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _result_snapshot(details: dict) -> list[tuple[str, str]]:
    ordered_keys = [
        "location",
        "variable_labels",
        "date_range",
        "row_count",
        "total_fields",
        "total_crops",
        "groups",
        "group_count",
    ]
    items: list[tuple[str, str]] = []
    for key in ordered_keys:
        value = details.get(key)
        if value in (None, "", [], {}):
            continue
        label = "Variables" if key == "variable_labels" else _format_label(key)
        items.append((label, _format_value(value)))
    return items


def _resolved_request_items(spec: dict) -> list[tuple[str, str]]:
    display_keys = _display_spec(spec)
    ordered_keys = [
        "task",
        "dataset",
        "location",
        "location_type",
        "variables",
        "crop_filter",
        "start_date",
        "end_date",
        "year",
        "interval",
        "aggregation",
        "compare_by",
        "split_by",
        "group_by",
        "station_id",
        "chart_type",
        "evidence_pattern",
    ]
    items: list[tuple[str, str]] = []
    for key in ordered_keys:
        value = display_keys.get(key)
        if value in (None, "", [], {}):
            continue
        items.append((_format_label(key), _format_value(value)))
    return items


def _render_definition_list(items: list[tuple[str, str]], columns: int = 2) -> None:
    if not items:
        return
    cols = st.columns(columns)
    for index, (label, value) in enumerate(items):
        with cols[index % columns]:
            st.markdown(f"**{label}**")
            st.caption(value)


def _init_state() -> None:
    defaults = _state_defaults()
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_header() -> None:
    st.set_page_config(
        page_title="SmartTap",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
            .smarttap-title {
                padding: 20px 24px;
                border-radius: 16px;
                background: linear-gradient(135deg, #101418 0%, #24333d 100%);
                color: #f8f5ef;
                margin-bottom: 1rem;
            }
            .smarttap-title h1 { margin: 0; color: #f8f5ef; }
            .smarttap-title p  { margin: 0.4rem 0 0; color: #d8d0c3; }

            /* Plain-English explanation card */
            .explanation-card {
                background: #f0f7f4;
                border-left: 4px solid #2e7d52;
                border-radius: 8px;
                padding: 14px 18px;
                margin-top: 12px;
                font-size: 1.0rem;
                line-height: 1.6;
                color: #1a1a1a;
            }
            .explanation-card .explain-label {
                font-size: 0.78rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: #2e7d52;
                margin-bottom: 6px;
            }
        </style>
        <div class="smarttap-title">
            <h1>SmartTap</h1>
            <p>Ask about Oregon agricultural and weather data. SmartTap will parse, fetch, validate, and visualize the result.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> None:
    with st.sidebar:
        st.subheader("What SmartTap Does")
        st.markdown(
            """
            - Builds charts from plain-English ag and weather questions
            - Shows a short explanation plus inspectable source rows
            - Supports crop summaries, trends, and comparisons
            """
        )

        st.subheader("Example Queries")
        st.markdown(
            """
            - `Show temperature in Corvallis for July 2024`
            - `What is the average ETa in Hood River in 2024?`
            - `What crops are grown in Benton County?`
            """
        )

        if st.button("Clear Results"):
            for key, value in _state_defaults().items():
                st.session_state[key] = value
            st.rerun()


def _append_result_message(query: str, result: dict) -> None:
    if result["success"]:
        task = result["spec"]["task"]
        st.session_state.messages.append({"role": "assistant", "content": f"Generated a `{task}` result for: {query}"})
    elif result.get("needs_confirmation"):
        st.session_state.messages.append({"role": "assistant", "content": result["confirmation_prompt"]})
    elif result.get("needs_clarification"):
        st.session_state.messages.append({"role": "assistant", "content": result["clarification_prompt"]})
    else:
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {result['error']}"})


def _clear_current_result() -> None:
    st.session_state.current_chart = None
    st.session_state.current_data = None
    st.session_state.current_details = None
    st.session_state.current_spec = None
    st.session_state.current_vega_spec = None
    st.session_state.current_files = None
    st.session_state.current_explanation = None
    st.session_state.current_secondary_views = None


def _apply_result(result: dict, query: str | None = None) -> None:
    if result["success"]:
        st.session_state.current_chart = result.get("chart_bytes")
        st.session_state.current_data = result.get("data_preview")
        st.session_state.current_details = result.get("summary")
        st.session_state.current_spec = result.get("spec")
        st.session_state.current_vega_spec = result.get("vega_spec")
        st.session_state.current_files = result.get("files")
        st.session_state.current_explanation = result.get("explanation", "")
        st.session_state.current_secondary_views = result.get("secondary_views", [])
        st.session_state.pending_spec = None
        st.session_state.confirmation_spec = None
        st.session_state.original_query = None
        st.session_state.followup_mode = None
        _close_confirmation_editor(st.session_state)
    elif result.get("needs_confirmation"):
        _clear_current_result()
        st.session_state.pending_spec = None
        st.session_state.confirmation_spec = result.get("spec")
        if query:
            st.session_state.original_query = st.session_state.original_query or query
        st.session_state.followup_mode = None
        _close_confirmation_editor(st.session_state)
    elif result.get("needs_clarification"):
        _clear_current_result()
        st.session_state.pending_spec = result.get("spec")
        st.session_state.confirmation_spec = None
        if query:
            st.session_state.original_query = st.session_state.original_query or query
        st.session_state.followup_mode = "clarification"
        _close_confirmation_editor(st.session_state)


def _run_query(query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.spinner("Running SmartTap..."):
        action = _next_query_action(
            query,
            followup_mode=st.session_state.followup_mode,
            pending_spec=st.session_state.pending_spec,
            original_query=st.session_state.original_query,
        )
        if action == "followup" and st.session_state.original_query:
            result = process_followup_reply(
                followup_query=query,
                pending_spec=st.session_state.pending_spec,
                original_query=st.session_state.original_query,
            )
        else:
            _clear_query_context(st.session_state)
            result = process_query(query)

    _apply_result(result, query=query)
    _append_result_message(query, result)


def _run_confirmation() -> None:
    if st.session_state.confirmation_spec is None or not st.session_state.original_query:
        return

    original_query = st.session_state.original_query
    with st.spinner("Running SmartTap..."):
        result = confirm_query(
            pending_spec=st.session_state.confirmation_spec,
            original_query=original_query,
        )

    _apply_result(result)
    _append_result_message(original_query, result)


def _run_confirmation_edit() -> None:
    if st.session_state.confirmation_spec is None or not st.session_state.original_query:
        return

    field = st.session_state.confirmation_edit_field or "crop"
    if field == "time_range":
        value = {
            "start_date": st.session_state.confirmation_edit_start_date,
            "end_date": st.session_state.confirmation_edit_end_date,
        }
    elif field == "metric":
        value = st.session_state.confirmation_edit_metric
    else:
        value = st.session_state.confirmation_edit_text

    with st.spinner("Updating request..."):
        result = apply_confirmation_edit(
            pending_spec=st.session_state.confirmation_spec,
            original_query=st.session_state.original_query,
            field=field,
            value=value,
        )

    _apply_result(result)
    _append_result_message(st.session_state.original_query, result)


def _render_chat() -> None:
    st.subheader("Chat")
    chat_container = st.container(height=420)
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    query = st.chat_input("Ask about Oregon weather, water, or crop patterns...")
    if query:
        _run_query(query)
        st.rerun()


def _render_explanation_card(explanation: str) -> None:
    if not explanation:
        return
    safe_explanation = escape(explanation)
    st.markdown(
        f"""
        <div class="explanation-card">
            <div class="explain-label"> What this means</div>
            {safe_explanation}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_result_details() -> None:
    details = st.session_state.current_details or {}
    spec = st.session_state.current_spec or {}
    if not details and not spec:
        return

    with st.expander("Result Details", expanded=False):
        if details:
            snapshot_items = _result_snapshot(details)
            if snapshot_items:
                st.markdown("**Snapshot**")
                _render_definition_list(snapshot_items, columns=2)

        if spec:
            st.markdown("**Resolved Request**")
            _render_definition_list(_resolved_request_items(spec), columns=2)


def _render_confirmation_editor(spec: dict) -> None:
    st.markdown("**Edit Request**")
    st.caption("Apply one deterministic change at a time, then confirm the refreshed request.")

    selected_field = st.selectbox(
        "Field",
        options=CONFIRMATION_EDIT_FIELDS,
        index=CONFIRMATION_EDIT_FIELDS.index(st.session_state.confirmation_edit_field or "crop"),
        format_func=lambda value: CONFIRMATION_EDIT_LABELS[value],
    )
    if selected_field != st.session_state.confirmation_edit_field:
        _seed_confirmation_editor_inputs(st.session_state, spec, selected_field)
        st.rerun()

    if selected_field == "crop":
        st.text_input("Crop", key="confirmation_edit_text", placeholder="Winter Wheat")
    elif selected_field == "location":
        st.text_input("Location", key="confirmation_edit_text", placeholder="Corvallis or Morrow County")
    elif selected_field == "time_range":
        st.date_input("Start date", key="confirmation_edit_start_date")
        st.date_input("End date", key="confirmation_edit_end_date")
    elif selected_field == "metric":
        metric_options = _metric_options()
        current_metric = st.session_state.confirmation_edit_metric
        if current_metric and current_metric not in metric_options:
            metric_options = [current_metric, *metric_options]
        st.selectbox(
            "Metric",
            options=metric_options,
            key="confirmation_edit_metric",
            format_func=_metric_option_label,
        )

    apply_col, cancel_col = st.columns(2)
    with apply_col:
        if st.button("Apply Change", use_container_width=True):
            _run_confirmation_edit()
            st.rerun()
    with cancel_col:
        if st.button("Cancel Edit", use_container_width=True):
            _close_confirmation_editor(st.session_state)
            st.rerun()


def _render_results() -> None:
    st.subheader("Results")

    if st.session_state.confirmation_spec is not None:
        spec = st.session_state.confirmation_spec
        st.warning("Confirmation required before SmartTap runs this request.")
        st.markdown(st.session_state.messages[-1]["content"] if st.session_state.messages else "")
        with st.expander("Resolved Request", expanded=True):
            _render_definition_list(_resolved_request_items(spec), columns=2)
        confirm_col, edit_col = st.columns(2)
        with confirm_col:
            if st.button("Confirm And Run", use_container_width=True):
                _run_confirmation()
                st.rerun()
        with edit_col:
            if st.button("Edit Request", use_container_width=True):
                _open_confirmation_editor(st.session_state)
                st.rerun()
        if st.session_state.confirmation_editor_open:
            _render_confirmation_editor(spec)
        st.divider()

    if st.session_state.current_chart:
        image = Image.open(io.BytesIO(st.session_state.current_chart))
        st.image(image, use_container_width=True)

        _render_explanation_card(st.session_state.current_explanation or "")

        st.download_button(
            "Download Chart",
            data=st.session_state.current_chart,
            file_name=f"smarttap_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            mime="image/png",
        )
    else:
        if st.session_state.confirmation_spec is None:
            st.info("Run a query to see a visualization.")

    secondary_views = st.session_state.current_secondary_views or []
    if secondary_views:
        st.subheader("Companion Views")
        for index, view in enumerate(secondary_views, start=1):
            st.markdown(f"**View {index}.** {view.get('caption', 'Companion chart')}")
            chart_bytes = view.get("chart_bytes")
            if chart_bytes:
                image = Image.open(io.BytesIO(chart_bytes))
                st.image(image, use_container_width=True)
            preview = view.get("data_preview")
            if preview is not None:
                with st.expander(f"Companion Data Preview {index}", expanded=False):
                    st.dataframe(preview, use_container_width=True, height=220)

    _render_result_details()

    if st.session_state.current_data is not None:
        with st.expander("Data Preview", expanded=True):
            st.dataframe(st.session_state.current_data, use_container_width=True, height=300)
            st.download_button(
                "Download Data (CSV)",
                data=st.session_state.current_data.to_csv(index=False),
                file_name=f"smarttap_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

    has_advanced = bool(st.session_state.current_vega_spec is not None or st.session_state.current_files or secondary_views)
    if has_advanced:
        with st.expander("Advanced", expanded=False):
            if st.session_state.current_vega_spec is not None:
                st.markdown("**Primary Vega-Lite Spec**")
                st.json(st.session_state.current_vega_spec)
                st.download_button(
                    "Download Vega Spec",
                    data=json.dumps(st.session_state.current_vega_spec, indent=2),
                    file_name=f"smarttap_spec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )

            for index, view in enumerate(secondary_views, start=1):
                if view.get("vega_spec") is not None:
                    with st.expander(f"Companion Vega-Lite Spec {index}", expanded=False):
                        st.json(view["vega_spec"])

            if st.session_state.current_files:
                st.markdown("**Saved Files**")
                for label, path in st.session_state.current_files.items():
                    if path:
                        st.markdown(f"**{label.title()}**: `{path}`")


def main() -> None:
    _init_state()
    _render_header()
    _render_sidebar()

    left, right = st.columns([1.0, 1.1], gap="large")
    with left:
        _render_chat()
    with right:
        _render_results()


if __name__ == "__main__":
    main()
