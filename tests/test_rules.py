from pathlib import Path

from app.ingestion import make_document
from app.rules import generate_rule_actions

DEMO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo"


def load_demo_documents():
    return [
        make_document(path.name, path.read_bytes())
        for path in sorted(DEMO_PATH.iterdir())
        if path.is_file()
    ]


def test_demo_links_invoice_contract_and_policy_evidence():
    actions = generate_rule_actions(load_demo_documents())
    discrepancy = next(item for item in actions if item.action_type == "financial_issue")
    assert discrepancy.title == "Invoice discrepancy"
    assert discrepancy.priority == "HIGH"
    assert "$600.00" in discrepancy.summary
    assert discrepancy.suggested_action == "Finance review"
    assert {citation.source for citation in discrepancy.evidence} >= {
        "customer_email.txt",
        "invoice_8821.txt",
        "contract.txt",
        "finance_policy.txt",
    }
    assert not discrepancy.missing_information


def test_demo_includes_deadline_and_open_ticket_actions():
    actions = generate_rule_actions(load_demo_documents())
    assert {item.action_type for item in actions} == {
        "financial_issue",
        "deadline",
        "customer_follow_up",
    }
    assert all(item.evidence for item in actions)


def test_unverified_billing_concern_does_not_claim_discrepancy():
    document = make_document(
        "customer_email.txt",
        b"I think our invoice is incorrect. Please take a look.",
    )
    actions = generate_rule_actions([document])
    invoice_action = next(item for item in actions if item.action_type == "financial_issue")
    assert invoice_action.title == "Verify reported invoice concern"
    assert invoice_action.evidence_confidence < 50
    assert "Original invoice with amount and reference" in invoice_action.missing_information
    assert invoice_action.priority != "HIGH"
