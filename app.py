from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app.analysis import analyze_documents
from app.config import PROJECT_ROOT, Settings
from app.ingestion import IngestionError, make_document, read_uploaded_file
from app.models import AnalysisResult, Document
from app.storage import (
    clear_workspace,
    get_latest_analysis,
    load_documents_for_analysis,
    save_analysis,
    update_action,
)
from ui.dashboard import render_dashboard
from ui.styles import configure_page

configure_page()

DEMO_DIRECTORY = PROJECT_ROOT / "data" / "demo"


def _load_settings() -> Settings:
    try:
        secrets = st.secrets.to_dict()
    except StreamlitSecretNotFoundError as exc:
        if exc.error_id != "no-secrets-found":
            raise
        secrets = {}
    return Settings.load(secrets)


settings = _load_settings()


def _load_demo_documents() -> list[Document]:
    documents = []
    for path in sorted(DEMO_DIRECTORY.iterdir()):
        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".json", ".csv", ".pdf"}:
            documents.append(make_document(path.name, path.read_bytes()))
    if not documents:
        raise IngestionError("The demo dataset is missing. Restore the files in data/demo and try again.")
    return documents


def _run_analysis(documents: list[Document]) -> None:
    with st.status("Building a unified, evidence-backed context…", expanded=True) as status:
        st.write("Reading sources and preparing searchable evidence chunks")
        st.write("Connecting related references, amounts, policies, dates, and open requests")
        result = analyze_documents(documents, settings)
        save_analysis(result, documents, settings)
        st.session_state["analysis_result"] = result.to_dict()
        st.session_state["documents"] = [
            {"source": document.source, "text": document.text} for document in documents
        ]
        status.update(label="Context analysis complete", state="complete", expanded=False)


def _get_result() -> AnalysisResult | None:
    saved = st.session_state.get("analysis_result")
    if saved:
        return AnalysisResult.from_dict(saved)
    result = get_latest_analysis(settings)
    if result:
        st.session_state["analysis_result"] = result.to_dict()
        documents = load_documents_for_analysis(result, settings)
        st.session_state["documents"] = [
            {"source": document.source, "text": document.text} for document in documents
        ]
    return result


def _change_status(item, status: str) -> None:
    updated = update_action(item, settings, status=status)
    result = _get_result()
    if result:
        for current in result.items:
            if current.id == item.id:
                current.status = updated.status
        st.session_state["analysis_result"] = result.to_dict()
    st.toast(f"{updated.title} marked {status.lower()}. No external action was taken.")
    st.rerun()


def _edit_action(item, suggested_action: str) -> None:
    updated = update_action(item, settings, suggested_action=suggested_action)
    result = _get_result()
    if result:
        for current in result.items:
            if current.id == item.id:
                current.suggested_action = updated.suggested_action
        st.session_state["analysis_result"] = result.to_dict()
    st.toast("Suggested action updated.")
    st.rerun()


def _try_demo() -> None:
    try:
        _run_analysis(_load_demo_documents())
    except IngestionError as exc:
        st.error(str(exc))
    except (ValueError, RuntimeError) as exc:
        st.error(f"Demo analysis could not be completed: {exc}")


with st.sidebar:
    st.markdown("### :material/folder_open: Data sources")
    uploaded_files = st.file_uploader(
        "Upload business documents",
        type=["pdf", "txt", "md", "json", "csv"],
        accept_multiple_files=True,
        help="Up to 10 MB per file. Scanned PDFs are not supported.",
    )
    if st.button("Analyze uploaded context", type="primary", icon=":material/troubleshoot:", width="stretch"):
        if not uploaded_files:
            st.warning("Choose at least one document first.")
        else:
            try:
                documents = [read_uploaded_file(uploaded_file) for uploaded_file in uploaded_files]
                _run_analysis(documents)
            except IngestionError as exc:
                st.error(str(exc))
            except (ValueError, RuntimeError) as exc:
                st.error(f"Analysis could not be completed: {exc}")

    if st.button("Load demo scenario", icon=":material/auto_awesome:", width="stretch"):
        _try_demo()

    st.caption("Local demo · 5 synthetic business records")
    if settings.llm_api_key and settings.llm_base_url:
        st.badge("Analyst API configured", icon=":material/cloud_done:", color="blue")
        st.caption("Source excerpts will be sent to the LLM endpoint configured in your environment.")
    else:
        st.badge("Local analysis mode", icon=":material/lock:", color="green")
        st.caption("No source documents are sent to an LLM in local-only mode.")

    with st.expander("Optional integrations"):
        st.code(
            "LLM_BASE_URL=https://api.openai.com/v1\n"
            "LLM_API_KEY=your_api_key_here\n"
            "LLM_MODEL=gpt-4o-mini",
            language="bash",
        )
        st.caption("Local BM25 search works by default. Optional local FAISS embeddings are documented in README.")

    with st.expander("Local workspace"):
        st.caption(f"SQLite database: {settings.database_path}")
        clear_confirmed = st.checkbox("I understand this deletes saved local records", key="clear-workspace-confirm")
        if st.button("Clear local workspace", disabled=not clear_confirmed, icon=":material/delete:"):
            clear_workspace(settings)
            st.session_state.pop("analysis_result", None)
            st.session_state.pop("documents", None)
            st.toast("Saved local records cleared.")
            st.rerun()

result = _get_result()
source_text = {
    item["source"]: item["text"]
    for item in st.session_state.get("documents", [])
}
render_dashboard(result, source_text, _try_demo, _change_status, _edit_action)
