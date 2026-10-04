from app.models import Chunk
from app.retrieval import LocalRetriever


def test_local_retriever_prefers_relevant_evidence():
    chunks = [
        Chunk("1", "invoice.txt", "Invoice INV-8821 total amount is $2,400."),
        Chunk("2", "contract.txt", "The contract monthly amount is $1,800."),
        Chunk("3", "support.txt", "A support ticket asks for an account contact update."),
    ]
    results = LocalRetriever(chunks, model_name="unused").search(
        "contract monthly amount $1,800", top_k=2
    )
    assert results
    assert results[0].source == "contract.txt"


def test_empty_search_returns_no_results():
    chunk = Chunk("1", "note.txt", "The account owner will review the contract.")
    retriever = LocalRetriever([chunk], model_name="unused")
    assert retriever.search("   ") == []
    assert retriever.search("invoice discrepancy") == []
