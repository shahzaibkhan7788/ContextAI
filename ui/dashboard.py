from __future__ import annotations

import json
from collections.abc import Callable

import streamlit as st

from app.models import AnalysisResult
from ui.components import render_action, render_header, render_metrics, render_source_list


def render_dashboard(
    result: AnalysisResult | None,
    source_text: dict[str, str],
    on_try_demo: Callable[[], None],
    on_status_change: Callable,
    on_action_edit: Callable,
) -> None:
    render_header(result)

    if result is None:
        st.space("large")
        with st.container(border=True):
            st.subheader("A clearer view of what needs attention", icon=":material/auto_awesome:")
            st.write(
                "Bring together emails, contracts, invoices, notes, and support tickets. "
                "ContextFlow connects their evidence and prepares a prioritized work queue for a person to review."
            )
            st.button(
                "Try the Acme demo",
                type="primary",
                icon=":material/play_arrow:",
                on_click=on_try_demo,
            )
        st.caption("Prototype boundaries: uploaded files only · no external integrations · no automatic actions.")
        return

    render_metrics(result)
    st.caption(f"Search indexed {result.chunk_count} evidence chunks across {result.source_count} sources.")

    for warning in result.warnings:
        st.warning(warning)
    if result.summary:
        with st.container(border=True):
            st.markdown("**Context summary**")
            st.write(result.summary)
            st.caption(
                "Recommendations are suggestions for human review. No email, payment, ticket, or external system is changed."
            )

    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"Analysis ID · {result.id[:12]}")
        st.download_button(
            "Export analysis",
            data=json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            file_name="contextflow-analysis.json",
            mime="application/json",
            icon=":material/download:",
        )

    queue_tab, sources_tab, method_tab = st.tabs(
        ["Work queue", "Source library", "How ContextFlow works"],
        key="contextflow-tabs",
    )

    with queue_tab:
        if result.llm_used:
            st.caption("The single ContextFlow Analyst supplemented deterministic checks with source-quote-validated suggestions.")
        statuses = ["All priorities", "HIGH", "MEDIUM", "LOW"]
        selected_priority = st.selectbox("Filter the work queue", statuses, key="priority-filter")
        visible_items = [
            item for item in result.items
            if selected_priority == "All priorities" or item.priority == selected_priority
        ]
        if not visible_items:
            st.success("No actions match this filter.")
        for item in visible_items:
            render_action(item, on_status_change, on_action_edit)
        if not result.items:
            st.info("No actionable items met the evidence threshold. Add more context or inspect the source library.")

    with sources_tab:
        st.subheader("Unified source library")
        st.write(
            "Every citation points back to the original uploaded file. "
            "Uploaded content is kept in this local prototype's SQLite database."
        )
        render_source_list(result, source_text)

    with method_tab:
        st.subheader("From scattered records to human-approved work")
        st.write(
            "One ContextFlow Analyst reviews retrieved evidence. Python handles parsing, retrieval, "
            "arithmetic, date normalization, evidence checks, priority safeguards, and local approval status."
        )
        st.code(
            "Files → parsing → chunks → local retrieval → ContextFlow Analyst (optional LLM)\n"
            "     → structured, source-checked suggestions → deterministic checks → human approval",
            language="text",
        )
        st.markdown("**Safety and prototype boundaries**")
        st.markdown(
            "- Recommendations show supporting source excerpts and missing information.\n"
            "- Evidence confidence describes support in the uploaded documents; it is not a calibrated probability.\n"
            "- Approval and ignore decisions are saved locally. They do not send messages or modify external systems.\n"
            "- No Gmail, Slack, Teams, CRM, payment, OCR, login, or background-worker integrations are implemented."
        )
