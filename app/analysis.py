from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.agent import AgentError, analyze_context
from app.config import Settings
from app.models import AnalysisResult, Document
from app.retrieval import LocalRetriever
from app.rules import extract_entities, generate_rule_actions

RETRIEVAL_QUERIES = (
    "invoice discrepancy billed amount customer reports charge contract monthly amount",
    "contract expiration renewal date deadline owner",
    "open pending support ticket customer follow up",
)


def analyze_documents(documents: list[Document], settings: Settings | None = None) -> AnalysisResult:
    if not documents:
        raise ValueError("Upload at least one readable document before analyzing.")
    settings = settings or Settings.load()
    if settings.require_llm and not (settings.llm_api_key and settings.llm_base_url):
        raise RuntimeError(
            "This hosted demo requires its LLM configuration. Contact the demo owner; do not enter an API key here."
        )
    all_chunks = [chunk for document in documents for chunk in document.chunks]
    if not all_chunks:
        raise ValueError("No searchable document text was found.")

    retriever = LocalRetriever(
        all_chunks,
        model_name=settings.embedding_model,
        use_faiss=settings.use_faiss,
    )
    retrieved_by_id = {}
    for query in RETRIEVAL_QUERIES:
        for chunk in retriever.search(query, top_k=5):
            retrieved_by_id[chunk.chunk_id] = chunk
    retrieved = list(retrieved_by_id.values())
    deterministic_items = [] if settings.require_llm else generate_rule_actions(documents)
    warnings: list[str] = []
    llm_used = False
    analyst_summary = ""

    if settings.llm_api_key and settings.llm_base_url:
        try:
            supplemental, analyst_summary = analyze_context(
                settings, documents, retrieved, deterministic_items
            )
            deterministic_items.extend(supplemental)
            llm_used = True
        except AgentError as exc:
            if settings.require_llm:
                raise RuntimeError(
                    f"Required LLM analysis failed: {exc} Deterministic analysis is disabled in this demo."
                ) from exc
            warnings.append(f"{exc} Rule-based analysis is still available.")
    elif settings.llm_api_key or settings.llm_base_url:
        warnings.append("LLM integration is only partially configured. Set both LLM_BASE_URL and LLM_API_KEY.")
    else:
        warnings.append("LLM is not configured. Deterministic analysis is running locally.")

    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    actions = sorted(deterministic_items, key=lambda item: (priority_order[item.priority], item.title.casefold()))
    entities = extract_entities(documents)
    company = next((entity for entity in entities if "@" not in entity and not entity.startswith("INV-")), "Business context")
    summary = analyst_summary or (
        f"ContextFlow reviewed {len(documents)} source documents and {len(all_chunks)} searchable evidence chunks. "
        f"It identified {len(actions)} candidate action{'s' if len(actions) != 1 else ''} for human review."
    )
    if not actions:
        summary += (
            " No suggestions met the source-evidence checks."
            if settings.require_llm
            else " No specific action cleared the available deterministic evidence checks."
        )

    return AnalysisResult(
        id=uuid4().hex,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        company=company,
        source_count=len(documents),
        chunk_count=len(all_chunks),
        entities=entities,
        items=actions,
        summary=summary,
        source_names=[document.source for document in documents],
        llm_used=llm_used,
        warnings=warnings,
    )
