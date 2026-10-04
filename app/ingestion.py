from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import PurePosixPath
from typing import BinaryIO

from pypdf import PdfReader

from app.models import Chunk, Document

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARACTERS = 200_000
CHUNK_SIZE = 1_000
CHUNK_OVERLAP = 150


class IngestionError(ValueError):
    """Raised when a provided document cannot be safely read."""


def _decode_text(raw: bytes, source: str) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionError(f"{source} is not valid UTF-8 text.") from exc


def _pdf_text(raw: bytes, source: str) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise IngestionError(f"Could not read {source} as a PDF: {exc}") from exc

    text = "\n\n".join(part.strip() for part in pages if part.strip())
    if not text:
        raise IngestionError(
            f"{source} has no extractable text. This prototype requires text-readable PDFs; scanned PDFs are not supported."
        )
    return text


def parse_bytes(source: str, raw: bytes) -> tuple[str, str]:
    source = PurePosixPath(source.replace("\\", "/")).name
    if source in {"", ".", ".."}:
        raise IngestionError("The uploaded file must have a valid filename.")
    if not raw:
        raise IngestionError(f"{source} is empty.")
    if len(raw) > MAX_FILE_BYTES:
        raise IngestionError(f"{source} exceeds the 10 MB per-file limit.")

    suffix = PurePosixPath(source.replace("\\", "/")).suffix.lower()
    if suffix == ".pdf":
        text = _pdf_text(raw, source)
        media_type = "application/pdf"
    elif suffix in {".txt", ".md"}:
        text = _decode_text(raw, source)
        media_type = "text/markdown" if suffix == ".md" else "text/plain"
    elif suffix == ".json":
        decoded = _decode_text(raw, source)
        try:
            text = json.dumps(json.loads(decoded), ensure_ascii=False, indent=2)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"{source} contains invalid JSON: {exc.msg}.") from exc
        media_type = "application/json"
    elif suffix == ".csv":
        decoded = _decode_text(raw, source)
        try:
            rows = list(csv.reader(io.StringIO(decoded)))
        except csv.Error as exc:
            raise IngestionError(f"{source} contains invalid CSV: {exc}.") from exc
        text = "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
        media_type = "text/csv"
    else:
        raise IngestionError(f"{source} has an unsupported format. Use PDF, TXT, MD, JSON, or CSV.")

    text = text.strip()
    if not text:
        raise IngestionError(f"{source} contains no readable text.")
    if len(text) > MAX_TEXT_CHARACTERS:
        raise IngestionError(f"{source} exceeds the {MAX_TEXT_CHARACTERS:,}-character text limit.")
    return text, media_type


def make_chunks(source: str, text: str) -> list[Chunk]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[Chunk] = []
    buffer = ""

    def add_chunk(value: str) -> None:
        normalized = value.strip()
        if not normalized:
            return
        index = len(chunks) + 1
        chunks.append(
            Chunk(
                chunk_id=f"{hashlib.sha1(source.encode('utf-8')).hexdigest()[:8]}-{index:03d}",
                source=source,
                text=normalized,
            )
        )

    for paragraph in paragraphs or [text]:
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= CHUNK_SIZE:
            buffer = candidate
            continue
        if buffer:
            add_chunk(buffer)
            buffer = ""

        start = 0
        while len(paragraph) - start > CHUNK_SIZE:
            split_at = paragraph.rfind(" ", start, start + CHUNK_SIZE)
            if split_at <= start + CHUNK_SIZE // 2:
                split_at = start + CHUNK_SIZE
            add_chunk(paragraph[start:split_at])
            start = max(start + 1, split_at - CHUNK_OVERLAP)
        buffer = paragraph[start:]

    if buffer:
        add_chunk(buffer)
    return chunks


def make_document(source: str, raw: bytes) -> Document:
    text, media_type = parse_bytes(source, raw)
    content_hash = hashlib.sha256(raw).hexdigest()
    return Document(
        source=source,
        text=text,
        content_hash=content_hash,
        chunks=make_chunks(source, text),
        media_type=media_type,
    )


def read_uploaded_file(uploaded_file: BinaryIO) -> Document:
    return make_document(uploaded_file.name, uploaded_file.getvalue())
