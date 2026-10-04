from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Sequence

from app.models import ActionItem, Document, Evidence

AMOUNT_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
INVOICE_RE = re.compile(r"\bINV(?:-\s*[A-Z0-9]{2,}|\s+[A-Z0-9]{2,}|[0-9]{2,})\b", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:,?\s+\d{4})?"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r")\b",
    re.IGNORECASE,
)
EXPECTED_TERMS = ("contract", "agreement", "monthly", "recurring", "per month", "contracted", "rate")
ACTUAL_TERMS = ("charged", "billed", "invoice total", "total due", "amount due", "invoiced", "paid")


def _action_id(title: str, action_type: str, sources: Sequence[str]) -> str:
    identity = "|".join((title.casefold(), action_type, *sorted(sources)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _line_for(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    line = text[start:] if end < 0 else text[start:end]
    offset = position - start
    boundaries = [match.end() for match in re.finditer(r"(?<=[.!?])\s+", line)]
    sentence_start = max((boundary for boundary in boundaries if boundary <= offset), default=0)
    sentence_end = min((boundary for boundary in boundaries if boundary > offset), default=len(line))
    return line[sentence_start:sentence_end].strip()


def _money_candidates(documents: Sequence[Document]) -> list[tuple[float, str, str, str]]:
    candidates: list[tuple[float, str, str, str]] = []
    for document in documents:
        for match in AMOUNT_RE.finditer(document.text):
            context = _line_for(document.text, match.start()).strip()
            lowered = context.casefold()
            if any(term in lowered for term in ("policy", "threshold", "greater than", "above $")):
                continue
            amount = float(match.group(1).replace(",", ""))
            candidates.append((amount, document.source, context, lowered))
    return candidates


def _invoice_refs(documents: Sequence[Document]) -> list[str]:
    refs = {
        re.sub(r"\s+", "-", match.group(0).upper())
        for document in documents
        for match in INVOICE_RE.finditer(document.text)
    }
    return sorted(refs)


def _evidence_for_amount(
    candidates: Sequence[tuple[float, str, str, str]], amount: float, terms: Sequence[str]
) -> list[Evidence]:
    found: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for value, source, quote, context in candidates:
        if value != amount or not any(term in context for term in terms):
            continue
        key = (source, quote)
        if key not in seen:
            found.append(Evidence(source=source, quote=quote))
            seen.add(key)
    return found


def _policy_threshold(documents: Sequence[Document]) -> tuple[float | None, Evidence | None]:
    threshold_re = re.compile(
        r"(?i)(?:greater than|above|over|exceed(?:s|ing)?|>)\s*\$\s*([\d,]+(?:\.\d{1,2})?)"
    )
    for document in documents:
        lowered = document.text.casefold()
        if not any(word in lowered for word in ("policy", "finance", "review threshold", "discrepanc")):
            continue
        match = threshold_re.search(document.text)
        if match:
            line = _line_for(document.text, match.start()).strip()
            return float(match.group(1).replace(",", "")), Evidence(document.source, line)
    return None, None


def _make_invoice_action(documents: Sequence[Document]) -> ActionItem | None:
    refs = _invoice_refs(documents)
    candidates = _money_candidates(documents)
    if not refs:
        return _make_unverified_invoice_action(documents)

    relevant_docs = [
        document
        for document in documents
        if any(ref.replace("-", "").casefold() in re.sub(r"[^a-z0-9]", "", document.text.casefold()) for ref in refs)
        or "contract" in document.source.casefold()
    ]
    relevant_candidates = [item for item in candidates if any(doc.source == item[1] for doc in relevant_docs)]
    expected = [
        item for item in relevant_candidates
        if any(term in item[3] for term in EXPECTED_TERMS)
    ]
    actual = [
        item for item in relevant_candidates
        if any(term in item[3] for term in ACTUAL_TERMS)
        or "invoice" in item[1].casefold()
    ]
    expected_values = sorted({item[0] for item in expected})
    actual_values = sorted({item[0] for item in actual})
    if not expected_values or not actual_values:
        return _make_unverified_invoice_action(documents, refs[0])

    expected_amount = expected_values[-1]
    actual_amount = actual_values[-1]
    difference = round(actual_amount - expected_amount, 2)
    if difference <= 0:
        return None

    relevant_source_names = {item[1] for item in expected + actual}
    evidence = _evidence_for_amount(relevant_candidates, expected_amount, EXPECTED_TERMS)
    evidence.extend(_evidence_for_amount(relevant_candidates, actual_amount, ACTUAL_TERMS))
    if not any(item.source.casefold().endswith((".pdf", ".txt", ".csv")) for item in evidence if "invoice" in item.source.casefold()):
        for item in _evidence_for_amount(relevant_candidates, actual_amount, ("invoice",)):
            if item not in evidence:
                evidence.append(item)

    threshold, policy_evidence = _policy_threshold(documents)
    missing: list[str] = []
    invoice_record_exists = any(
        "invoice" in source.casefold()
        and any(evidence_item.source == source for evidence_item in evidence)
        for source in relevant_source_names
    )
    if not invoice_record_exists:
        missing.append("Original invoice document")
    if policy_evidence:
        evidence.append(policy_evidence)
    else:
        missing.append("Finance policy or review threshold")

    high_priority = threshold is not None and difference > threshold
    priority = "HIGH" if high_priority else "MEDIUM"
    suggested_action = "Finance review" if high_priority else "Verify the invoice and contract amounts"
    facts = [
        f"Invoice reference: {refs[0]}",
        f"Contract / expected amount: ${expected_amount:,.2f}",
        f"Reported / invoiced amount: ${actual_amount:,.2f}",
        f"Calculated difference: ${difference:,.2f}",
    ]
    if threshold is not None:
        facts.append(f"Finance review threshold: greater than ${threshold:,.2f}")
    confidence = 68 + min(8, len({item.source for item in evidence}) * 4)
    if invoice_record_exists:
        confidence += 8
    if policy_evidence:
        confidence += 8
    if missing:
        confidence -= 10 * len(missing)
    confidence = max(35, min(confidence, 96))
    reason = (
        f"The documents link {refs[0]} to an expected amount of ${expected_amount:,.2f} and a reported "
        f"amount of ${actual_amount:,.2f}. The difference is calculated from those source amounts."
    )
    if high_priority and threshold is not None:
        reason += f" The finance policy requires review above ${threshold:,.2f}."
    elif not policy_evidence:
        reason += " No finance review threshold was found, so high priority is not inferred from policy."

    sources = [item.source for item in evidence]
    return ActionItem(
        id=_action_id("Invoice discrepancy", "financial_issue", sources),
        title="Invoice discrepancy",
        action_type="financial_issue",
        priority=priority,
        summary=f"{refs[0]} differs from the contract amount by ${difference:,.2f}.",
        suggested_action=suggested_action,
        evidence_confidence=confidence,
        facts=facts,
        evidence=_unique_evidence(evidence),
        missing_information=missing,
        response_draft=(
            "Hi,\n\nThank you for flagging the amount associated with "
            f"{refs[0]}. We have identified a difference between the reported amount and the contract amount. "
            "Our finance team will review the supporting documents before we confirm a correction.\n\n"
            "We will follow up once that review is complete.\n\nBest regards,\nFinance Team"
        ),
        reason=reason,
    )


def _make_unverified_invoice_action(documents: Sequence[Document], invoice_ref: str = "") -> ActionItem | None:
    triggers = ("invoice", "billing", "charged", "incorrect", "discrepanc")
    for document in documents:
        lowered = document.text.casefold()
        if any(term in lowered for term in triggers):
            quote = next(
                (line.strip() for line in document.text.splitlines() if any(term in line.casefold() for term in triggers)),
                document.text[:240],
            )
            reference = invoice_ref or "the reported invoice"
            return ActionItem(
                id=_action_id("Verify reported invoice concern", "financial_issue", [document.source]),
                title="Verify reported invoice concern",
                action_type="financial_issue",
                priority="MEDIUM",
                summary="A billing concern is mentioned, but there is not enough source evidence to confirm an amount discrepancy.",
                suggested_action="Request or locate the original invoice",
                evidence_confidence=42,
                facts=[f"Reference mentioned: {reference}"],
                evidence=[Evidence(document.source, quote)],
                missing_information=["Original invoice with amount and reference", "Contracted amount or agreed pricing"],
                response_draft=(
                    "Hi,\n\nThank you for bringing this billing concern to our attention. "
                    "Could you please share the invoice or invoice number so we can compare it with the agreed amount?\n\n"
                    "Best regards,\nFinance Team"
                ),
                reason="The available documents mention a concern but do not establish the original invoice amount or contracted amount.",
            )
    return None


def _unique_evidence(evidence: Sequence[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    result: list[Evidence] = []
    for item in evidence:
        key = (item.source, item.quote)
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _parse_expiry_date(raw: str) -> tuple[date | None, bool]:
    value = raw.replace(",", " ").strip()
    formats = (
        "%B %d %Y", "%b %d %Y", "%B %d", "%b %d",
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y",
    )
    today = date.today()
    for date_format in formats:
        try:
            parsed = datetime.strptime(value, date_format).date()
        except ValueError:
            continue
        if "%Y" not in date_format and "%y" not in date_format:
            assumed_year = today.year if (parsed.month, parsed.day) >= (today.month, today.day) else today.year + 1
            parsed = parsed.replace(year=assumed_year)
            return parsed, True
        return parsed, False
    return None, False


def _make_renewal_action(documents: Sequence[Document]) -> ActionItem | None:
    expiry_terms = re.compile(r"(?i)\b(?:expires|expiry|expiration|renewal date|renew by)\b")
    for document in documents:
        term = expiry_terms.search(document.text)
        if not term:
            continue
        date_match = DATE_RE.search(document.text, term.start())
        if not date_match:
            continue
        parsed, year_assumed = _parse_expiry_date(date_match.group(0))
        if not parsed:
            continue

        days_left = (parsed - date.today()).days
        priority = "HIGH" if 0 <= days_left <= 7 else "MEDIUM" if days_left <= 45 else "LOW"
        if days_left < 0:
            priority = "MEDIUM"
        evidence = [Evidence(document.source, _line_for(document.text, term.start()).strip())]
        missing = ["Expiry year is not stated; the nearest upcoming year is assumed."] if year_assumed else []
        confidence = 78 if not year_assumed else 69
        confidence += 5 if any(word in document.text.casefold() for word in ("contract", "agreement")) else 0
        return ActionItem(
            id=_action_id("Contract renewal", "deadline", [document.source]),
            title="Contract renewal",
            action_type="deadline",
            priority=priority,
            summary=f"The contract has a renewal or expiry date of {parsed.strftime('%b %d, %Y')}.",
            suggested_action="Review renewal requirements and notify the account owner",
            evidence_confidence=confidence,
            facts=[f"Date stated in source: {date_match.group(0)}", f"Normalized date: {parsed.isoformat()}"],
            evidence=evidence,
            missing_information=missing,
            response_draft=(
                "Hi,\n\nWe are reviewing the upcoming contract renewal date and the applicable renewal requirements. "
                "We will confirm the next steps with you before the stated expiry date.\n\nBest regards,\nAccount Team"
            ),
            reason=(
                f"The source explicitly labels {date_match.group(0)} as an expiry or renewal date. "
                + (f"There are {days_left} days remaining." if days_left >= 0 else "The stated date has passed and needs confirmation.")
            ),
        )
    return None


def _make_support_action(documents: Sequence[Document]) -> ActionItem | None:
    for document in documents:
        text = document.text
        lowered = text.casefold()
        looks_like_ticket = any(word in lowered for word in ("support ticket", '"status"', "ticket_id", "ticket id"))
        is_open = any(word in lowered for word in ('"open"', '"pending"', "status: open", "status: pending"))
        if looks_like_ticket and is_open:
            quote = next(
                (line.strip() for line in text.splitlines() if any(word in line.casefold() for word in ("open", "pending", "follow up", "follow-up"))),
                text[:240],
            )
            evidence = [Evidence(document.source, quote)]
            return ActionItem(
                id=_action_id("Open support follow-up", "customer_follow_up", [document.source]),
                title="Open support follow-up",
                action_type="customer_follow_up",
                priority="LOW",
                summary="A support ticket is marked open or pending and may need a human follow-up.",
                suggested_action="Review the ticket and prepare a customer update",
                evidence_confidence=72,
                facts=[quote],
                evidence=evidence,
                missing_information=["Ticket owner or next response date"],
                response_draft=(
                    "Hi,\n\nThank you for your patience. We are reviewing your open support request and will share "
                    "an update as soon as we have confirmed the next steps.\n\nBest regards,\nSupport Team"
                ),
                reason="The provided ticket record indicates an open or pending status. No message is sent by this prototype.",
            )
    return None


def generate_rule_actions(documents: Sequence[Document]) -> list[ActionItem]:
    actions = [
        _make_invoice_action(documents),
        _make_renewal_action(documents),
        _make_support_action(documents),
    ]
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(
        [item for item in actions if item is not None],
        key=lambda item: (priority_order[item.priority], item.title.casefold()),
    )


def extract_entities(documents: Sequence[Document]) -> list[str]:
    patterns = (
        re.compile(r"\b[A-Z][A-Za-z&'.-]*(?:\s+[A-Z][A-Za-z&'.-]*)*\s+(?:Corporation|Corp\.?|Inc\.?|LLC|Ltd\.?|Company)\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    )
    entities: set[str] = set()
    for document in documents:
        for pattern in patterns:
            entities.update(match.group(0).strip() for match in pattern.finditer(document.text))
    entities.update(_invoice_refs(documents))
    return sorted(entities, key=str.casefold)
