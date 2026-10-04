from dataclasses import replace

import pytest
import requests

from app.agent import AgentError, analyze_context
from app.config import Settings
from app.ingestion import make_document


class FakeErrorResponse:
    status_code = 404

    def json(self):
        return {"error": {"message": "Model not found"}}

    def raise_for_status(self):
        raise requests.HTTPError("Not found", response=self)


def test_llm_http_error_includes_provider_detail_and_redacts_key(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeErrorResponse())
    settings = replace(Settings.load(), llm_api_key="private-test-key")
    document = make_document("source.txt", b"A short business record for review.")

    with pytest.raises(AgentError) as error:
        analyze_context(settings, [document], [], [])

    assert "failed (404): Model not found" in str(error.value)
    assert "private-test-key" not in str(error.value)
