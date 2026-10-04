from dataclasses import replace

import pytest

from app.analysis import analyze_documents
from app.agent import AgentError
from app.config import Settings
from app.ingestion import make_document


def test_demo_mode_always_requires_llm(monkeypatch):
    monkeypatch.delenv("CONTEXTFLOW_DEMO_MODE", raising=False)
    monkeypatch.delenv("CONTEXTFLOW_REQUIRE_LLM", raising=False)
    settings = Settings.load(
        {
            "CONTEXTFLOW_DEMO_MODE": "true",
            "CONTEXTFLOW_REQUIRE_LLM": "false",
            "DEMO_USERNAME": "reviewer",
            "DEMO_PASSWORD": "test-password",
        }
    )

    assert settings.demo_mode is True
    assert settings.require_llm is True


def test_llm_required_mode_uses_model_actions_without_deterministic_rules(monkeypatch, tmp_path):
    import app.analysis as analysis

    document = make_document("record.txt", b"Customer asked for a follow-up.")
    settings = replace(
        Settings.load(),
        llm_base_url="https://llm.example/v1",
        llm_api_key="test-key",
        require_llm=True,
        data_dir=tmp_path,
        database_path=tmp_path / "unused.sqlite3",
    )

    class FakeRetriever:
        def __init__(self, chunks, **kwargs):
            self.chunks = chunks

        def search(self, query, top_k):
            return self.chunks[:1]

    monkeypatch.setattr(analysis, "LocalRetriever", FakeRetriever)
    monkeypatch.setattr(
        analysis,
        "generate_rule_actions",
        lambda documents: pytest.fail("LLM-required mode must not run deterministic action rules."),
    )
    observed = {}

    def fake_analyze_context(settings, documents, chunks, deterministic_items):
        observed["deterministic_items"] = deterministic_items
        return [], "LLM reviewed the supplied record."

    monkeypatch.setattr(analysis, "analyze_context", fake_analyze_context)

    result = analyze_documents([document], settings)

    assert observed["deterministic_items"] == []
    assert result.llm_used is True
    assert "LLM reviewed" in result.summary
    assert not settings.database_path.exists()


def test_llm_required_mode_fails_clearly_without_provider_secrets():
    settings = replace(Settings.load(), require_llm=True, llm_base_url="", llm_api_key="")
    document = make_document("record.txt", b"Customer asked for a follow-up.")

    with pytest.raises(RuntimeError, match="requires its LLM configuration"):
        analyze_documents([document], settings)


def test_llm_required_mode_does_not_claim_deterministic_fallback(monkeypatch):
    import app.analysis as analysis

    document = make_document("record.txt", b"Customer asked for a follow-up.")
    settings = replace(
        Settings.load(),
        llm_base_url="https://llm.example/v1",
        llm_api_key="test-key",
        require_llm=True,
    )

    class FakeRetriever:
        def __init__(self, chunks, **kwargs):
            self.chunks = chunks

        def search(self, query, top_k):
            return self.chunks[:1]

    monkeypatch.setattr(analysis, "LocalRetriever", FakeRetriever)
    monkeypatch.setattr(analysis, "generate_rule_actions", lambda documents: [])
    monkeypatch.setattr(
        analysis,
        "analyze_context",
        lambda *args: (_ for _ in ()).throw(AgentError("The configured LLM request failed (404).")),
    )

    with pytest.raises(RuntimeError, match="Deterministic analysis is disabled"):
        analyze_documents([document], settings)
