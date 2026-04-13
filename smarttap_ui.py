from __future__ import annotations

import io
import json
from html import escape
from datetime import datetime

import streamlit as st
from PIL import Image

from smarttap_service import process_clarification_reply, process_query


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
        "pending_spec": None,
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
            - Time series charts
            - Statistical summaries
            - Crop summaries by city or county
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
            for key in [
                "messages",
                "current_chart",
                "current_data",
                "current_details",
                "current_spec",
                "current_vega_spec",
                "current_files",
                "current_explanation",
                "pending_spec",
                "original_query",
            ]:
                st.session_state[key] = [] if key == "messages" else None
            st.rerun()


def _append_result_message(query: str, result: dict) -> None:
    if result["success"]:
        task = result["spec"]["task"]
        st.session_state.messages.append({"role": "assistant", "content": f"Generated a `{task}` result for: {query}"})
    elif result.get("needs_clarification"):
        st.session_state.messages.append({"role": "assistant", "content": result["clarification_prompt"]})
    else:
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {result['error']}"})


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
            result = process_query(query)

    if result["success"]:
        st.session_state.current_chart       = result.get("chart_bytes")
        st.session_state.current_data        = result.get("data_preview")
        st.session_state.current_details     = result.get("summary")
        st.session_state.current_spec        = result.get("spec")
        st.session_state.current_vega_spec   = result.get("vega_spec")
        st.session_state.current_files       = result.get("files")
        st.session_state.current_explanation = result.get("explanation", "")
        st.session_state.pending_spec        = None
        st.session_state.original_query      = None
    elif result.get("needs_clarification"):
        st.session_state.pending_spec = result.get("spec")
        st.session_state.original_query = st.session_state.original_query or query

    _append_result_message(query, result)


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
            <div class="explain-label">📖 What this means</div>
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
            display_keys = [
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
            ]
            for key in display_keys:
                value = spec.get(key)
                if value in (None, "", [], {}):
                    continue
                st.markdown(f"**{key.replace('_', ' ').title()}**: {value}")


def _render_results() -> None:
    st.subheader("Results")

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
        st.info("Run a query to see a visualization.")

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
