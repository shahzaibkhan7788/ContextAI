from __future__ import annotations

from collections.abc import Callable, Sequence

import streamlit as st

from app.models import ActionItem, AnalysisResult, Evidence

PRIORITY_COLOR = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
STATUS_COLOR = {"Pending": "orange", "Approved": "green", "Ignored": "gray"}


def render_header(result: AnalysisResult | None) -> None:
    st.title("ContextFlow", icon=":material/flowchart:")
    st.caption("AI context & action engine · Turn scattered information into the next right action.")
    if result:
        st.markdown(
            f"**{result.company}** &nbsp; · &nbsp; {result.source_count} source documents "
            f"&nbsp; · &nbsp; Updated {result.created_at.replace('T', ' ').replace('+00:00', ' UTC')}"
        )


def render_metrics(result: AnalysisResult) -> None:
    total = len(result.items)
    high = sum(item.priority == "HIGH" for item in result.items)
    medium = sum(item.priority == "MEDIUM" for item in result.items)
    low = sum(item.priority == "LOW" for item in result.items)
    first, second, third, fourth = st.columns(4)
    first.metric("Actions to review", total, border=True)
    second.metric("High priority", high, border=True)
    third.metric("Medium priority", medium, border=True)
    fourth.metric("Low priority", low, border=True)


def render_evidence(evidence: Sequence[Evidence]) -> None:
    if not evidence:
        st.info("No source evidence is attached to this suggestion.")
        return
    for citation in evidence:
        with st.container(border=True):
            st.markdown(f"**{citation.source}**")
            st.markdown(f"> {citation.quote}")
            if citation.chunk_id:
                st.caption(f"Evidence chunk · {citation.chunk_id}")


def render_action(
    item: ActionItem,
    on_status_change: Callable[[ActionItem, str], None],
    on_action_edit: Callable[[ActionItem, str], None],
) -> None:
    with st.container(border=True):
        heading, status = st.columns([4, 1])
        with heading:
            st.badge(item.priority, color=PRIORITY_COLOR.get(item.priority, "gray"))
            st.subheader(item.title)
        with status:
            st.badge(item.status, color=STATUS_COLOR.get(item.status, "gray"))

        st.write(item.summary)
        st.markdown(f"**Suggested next step:** {item.suggested_action}")
        st.caption(f"Evidence confidence · {item.evidence_confidence}/100 · based on source coverage, not a calibrated probability")

        if item.facts:
            st.markdown("**What the sources say**")
            for fact in item.facts:
                st.markdown(f"- {fact}")

        if item.missing_information:
            st.warning("Information to confirm: " + " · ".join(item.missing_information), icon=":material/visibility_off:")

        with st.expander(f"Why this action? · {len(item.evidence)} evidence excerpts"):
            st.markdown(item.reason)
            render_evidence(item.evidence)

        if item.response_draft:
            with st.expander("Prepare a customer response draft"):
                st.caption("Draft only. ContextFlow will not send this message.")
                st.code(item.response_draft, language="text")
                st.download_button(
                    "Download draft",
                    data=item.response_draft,
                    file_name="contextflow_response_draft.txt",
                    mime="text/plain",
                    key=f"download-{item.id}",
                    icon=":material/download:",
                )

        with st.expander("Edit suggested action"):
            edited_action = st.text_input(
                "Suggested action",
                value=item.suggested_action,
                max_chars=180,
                key=f"edit-text-{item.id}",
            )
            if st.button("Save edit", key=f"edit-save-{item.id}", icon=":material/edit:"):
                on_action_edit(item, edited_action)

        if item.status == "Pending":
            approve, ignore = st.columns(2)
            if approve.button(
                "Approve for follow-up",
                key=f"approve-{item.id}",
                type="primary",
                icon=":material/check_circle:",
            ):
                on_status_change(item, "Approved")
            if ignore.button(
                "Ignore",
                key=f"ignore-{item.id}",
                icon=":material/archive:",
            ):
                on_status_change(item, "Ignored")
        else:
            st.caption("Human decision recorded locally. No external system or customer was contacted.")


def render_source_list(result: AnalysisResult, source_text: dict[str, str]) -> None:
    for name in result.source_names:
        text = source_text.get(name, "")
        citations = sum(
            1 for item in result.items for evidence in item.evidence if evidence.source == name
        )
        with st.container(border=True):
            title, count = st.columns([4, 1])
            with title:
                st.markdown(f"**{name}**")
                st.caption(f"{len(text):,} characters · {citations} evidence citations")
            with count:
                st.badge("Referenced" if citations else "Context", color="blue" if citations else "gray")
            if text:
                with st.expander("Read extracted text"):
                    st.text(text[:12_000])
                    if len(text) > 12_000:
                        st.caption("Preview shortened to 12,000 characters.")
                    st.download_button(
                        "Download extracted text",
                        data=text,
                        file_name=name.rsplit(".", 1)[0] + ".txt",
                        mime="text/plain",
                        key=f"source-download-{name}",
                    )
