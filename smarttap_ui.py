from __future__ import annotations

import io
import json
from html import escape
from datetime import datetime

import streamlit as st
from PIL import Image

from smarttap_service import confirm_query, process_clarification_reply, process_query


def _looks_like_new_query(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    if len(lowered.split()) <= 2 and all(token.isalpha() for token in lowered.split()):
        return False
    return True


def _display_spec(spec: dict) -> dict:
    hidden_keys = {"notes"}
    display = {}
    for key, value in (spec or {}).items():
        if key in hidden_keys:
            continue
        if value in (None, "", [], {}):
            continue
        display[key] = value
    return display


def _init_state() -> None:
    defaults = {
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
    }
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
        st.subheader("Supported Tasks")
        st.markdown(
            """
            - Evidence-oriented time series charts
            - Statistical snapshots
            - Crop ranking and distribution summaries
            - Multi-variable comparisons
            - Coordinated cross-dataset evidence packages
            """
        )

        st.caption(
            "Canonical taxonomy also tracks next-step patterns: "
            "`comparison_grouped`, `change_over_period`, `ranking_metric`, and `seasonality_pattern`."
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
            for key in [
                "messages",
                "current_chart",
                "current_data",
                "current_details",
                "current_spec",
                "current_vega_spec",
                "current_files",
                "current_explanation",
                "current_secondary_views",
                "pending_spec",
                "confirmation_spec",
                "original_query",
            ]:
                st.session_state[key] = [] if key == "messages" else None
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
    elif result.get("needs_confirmation"):
        _clear_current_result()
        st.session_state.pending_spec = None
        st.session_state.confirmation_spec = result.get("spec")
        if query:
            st.session_state.original_query = st.session_state.original_query or query
    elif result.get("needs_clarification"):
        _clear_current_result()
        st.session_state.pending_spec = result.get("spec")
        st.session_state.confirmation_spec = None
        if query:
            st.session_state.original_query = st.session_state.original_query or query


def _run_query(query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.spinner("Running SmartTap..."):
        if st.session_state.pending_spec is not None and st.session_state.original_query:
            result = process_clarification_reply(
                followup_query=query,
                pending_spec=st.session_state.pending_spec,
                original_query=st.session_state.original_query,
            )
        else:
            if st.session_state.confirmation_spec is not None:
                st.session_state.confirmation_spec = None
                st.session_state.original_query = None
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

    with st.expander("Result Details", expanded=True):
        if details:
            st.markdown("**Metadata**")
            for key, value in details.items():
                if key == "variables_list":
                    continue
                st.markdown(f"**{key.replace('_', ' ').title()}**: {value}")

        if spec:
            st.markdown("**Resolved Request**")
            display_keys = _display_spec(spec)
            ordered_keys = [
                "task",
                "dataset",
                "location",
                "location_type",
                "station_id",
                "variables",
                "start_date",
                "end_date",
                "year",
                "interval",
                "chart_type",
                "aggregation",
                "crop_filter",
                "evidence_pattern",
                "group_by",
                "compare_by",
                "split_by",
                "secondary_variables",
                "source_datasets",
                "chart_package",
                "clarification_needed",
            ]
            for key in ordered_keys:
                value = display_keys.get(key)
                if value in (None, "", [], {}):
                    continue
                st.markdown(f"**{key.replace('_', ' ').title()}**: {value}")


def _render_results() -> None:
    st.subheader("Results")

    if st.session_state.confirmation_spec is not None:
        spec = st.session_state.confirmation_spec
        st.warning("Confirmation required before SmartTap runs this request.")
        st.markdown(st.session_state.messages[-1]["content"] if st.session_state.messages else "")
        with st.expander("Resolved Request", expanded=True):
            for key, value in _display_spec(spec).items():
                st.markdown(f"**{key.replace('_', ' ').title()}**: {value}")
        confirm_col, edit_col = st.columns(2)
        with confirm_col:
            if st.button("Confirm And Run", use_container_width=True):
                _run_confirmation()
                st.rerun()
        with edit_col:
            if st.button("Edit Request", use_container_width=True):
                st.session_state.confirmation_spec = None
                st.session_state.original_query = None
                st.info("Enter a revised query in the chat to update the request.")
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
                with st.expander(f"Companion Data Preview {index}"):
                    st.dataframe(preview, use_container_width=True, height=220)
            if view.get("vega_spec") is not None:
                with st.expander(f"Companion Vega-Lite Spec {index}"):
                    st.json(view["vega_spec"])

    _render_result_details()

    if st.session_state.current_data is not None:
        st.subheader("Data Preview")
        st.dataframe(st.session_state.current_data, use_container_width=True, height=300)
        st.download_button(
            "Download Data (CSV)",
            data=st.session_state.current_data.to_csv(index=False),
            file_name=f"smarttap_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

    if st.session_state.current_vega_spec is not None:
        with st.expander("Vega-Lite Spec"):
            st.json(st.session_state.current_vega_spec)
            st.download_button(
                "Download Vega Spec",
                data=json.dumps(st.session_state.current_vega_spec, indent=2),
                file_name=f"smarttap_spec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

    if st.session_state.current_files:
        with st.expander("Saved Files"):
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
