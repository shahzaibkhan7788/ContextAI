from app.config import Settings
from app.models import ActionItem, AnalysisResult, Document, Evidence
from app.storage import (
    clear_workspace,
    get_latest_analysis,
    load_documents_for_analysis,
    save_analysis,
    update_action,
)


def make_settings(tmp_path):
    return Settings(
        llm_base_url="",
        llm_api_key="",
        llm_model="test-model",
        embedding_model="unused",
        use_faiss=False,
        data_dir=tmp_path,
        database_path=tmp_path / "test.sqlite3",
    )


def test_action_decisions_and_source_documents_persist(tmp_path):
    settings = make_settings(tmp_path)
    document = Document("email.txt", "Please review invoice INV-8821.", "sha256")
    item = ActionItem(
        id="stable-action",
        title="Invoice review",
        action_type="financial_issue",
        priority="MEDIUM",
        summary="An invoice is mentioned.",
        suggested_action="Review source",
        evidence_confidence=60,
        evidence=[Evidence("email.txt", "Please review invoice INV-8821.")],
    )
    result = AnalysisResult(
        id="analysis-1",
        created_at="2026-10-04T00:00:00+00:00",
        company="Example Corp",
        source_count=1,
        chunk_count=1,
        entities=[],
        items=[item],
        summary="One action needs review.",
        source_names=["email.txt"],
    )
    save_analysis(result, [document], settings)
    update_action(item, settings, suggested_action="Request the invoice", status="Approved")

    latest = get_latest_analysis(settings)
    assert latest is not None
    assert latest.items[0].status == "Approved"
    assert latest.items[0].suggested_action == "Request the invoice"
    assert [source.source for source in load_documents_for_analysis(latest, settings)] == ["email.txt"]

    clear_workspace(settings)
    assert get_latest_analysis(settings) is None
