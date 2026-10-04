import json
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.ingestion import IngestionError, make_document, make_chunks, parse_bytes


@pytest.mark.parametrize(
    ("name", "raw", "expected"),
    [
        ("note.txt", b"Account needs a follow-up.", "Account needs a follow-up."),
        ("note.md", b"# Renewal\nExpires October 21.", "# Renewal\nExpires October 21."),
        ("ticket.json", b'{"status": "open"}', '"status": "open"'),
        ("amounts.csv", b"Invoice,Amount\nINV-1,$100", "Invoice | Amount"),
    ],
)
def test_supported_text_formats(name, raw, expected):
    text, media_type = parse_bytes(name, raw)
    assert expected in text
    assert media_type
    assert make_document(name, raw).chunks


def test_json_is_pretty_printed():
    text, _ = parse_bytes("ticket.json", json.dumps({"status": "open"}).encode())
    assert '"status": "open"' in text


def test_invalid_json_is_reported():
    with pytest.raises(IngestionError, match="invalid JSON"):
        parse_bytes("ticket.json", b"{broken")


def test_image_only_pdf_reports_no_ocr_support():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    content = BytesIO()
    writer.write(content)
    with pytest.raises(IngestionError, match="text-readable PDFs"):
        parse_bytes("scanned.pdf", content.getvalue())


def test_chunks_are_source_attributed_and_bounded():
    text = " ".join(f"evidence{index}" for index in range(700))
    chunks = make_chunks("long.txt", text)
    assert len(chunks) > 1
    assert all(chunk.source == "long.txt" for chunk in chunks)
    assert all(chunk.chunk_id for chunk in chunks)
    assert all(len(chunk.text) <= 1_000 for chunk in chunks)
