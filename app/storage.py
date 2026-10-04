from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Sequence

from app.config import Settings
from app.models import ActionItem, AnalysisResult, Document


def connect(settings: Settings | None = None) -> sqlite3.Connection:
    settings = settings or Settings.load()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(settings: Settings | None = None) -> None:
    with connect(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                source TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                text TEXT NOT NULL,
                media_type TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            );
            """
        )


def save_analysis(
    result: AnalysisResult,
    documents: Sequence[Document],
    settings: Settings | None = None,
) -> None:
    initialize_database(settings)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with connect(settings) as connection:
        for document in documents:
            connection.execute(
                """
                INSERT INTO documents (source, content_hash, text, media_type, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    text = excluded.text,
                    media_type = excluded.media_type,
                    updated_at = excluded.updated_at
                """,
                (document.source, document.content_hash, document.text, document.media_type, now),
            )
        connection.execute(
            "INSERT INTO analyses (id, created_at, payload_json) VALUES (?, ?, ?)",
            (result.id, result.created_at, json.dumps(result.to_dict(), ensure_ascii=False)),
        )
        for item in result.items:
            connection.execute(
                """
                INSERT INTO actions (id, analysis_id, status, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    analysis_id = excluded.analysis_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (item.id, result.id, item.status, json.dumps(item.to_dict(), ensure_ascii=False), now),
            )


def update_action(
    item: ActionItem,
    settings: Settings | None = None,
    suggested_action: str | None = None,
    status: str | None = None,
) -> ActionItem:
    if status is not None and status not in {"Pending", "Approved", "Ignored"}:
        raise ValueError("Action status must be Pending, Approved, or Ignored.")
    with connect(settings) as connection:
        row = connection.execute("SELECT payload_json FROM actions WHERE id = ?", (item.id,)).fetchone()
        if row is None:
            raise LookupError("This action is not saved in the local workspace.")
        from app.models import ActionItem as ActionItemModel

        saved = ActionItemModel.from_dict(json.loads(row["payload_json"]))
        if suggested_action is not None:
            cleaned = suggested_action.strip()
            if not cleaned or len(cleaned) > 180:
                raise ValueError("A suggested action is required and must be 180 characters or fewer.")
            saved.suggested_action = cleaned
        if status is not None:
            saved.status = status
        connection.execute(
            "UPDATE actions SET status = ?, payload_json = ?, updated_at = ? WHERE id = ?",
            (
                saved.status,
                json.dumps(saved.to_dict(), ensure_ascii=False),
                datetime.now(UTC).isoformat(timespec="seconds"),
                saved.id,
            ),
        )
    return saved


def get_latest_analysis(settings: Settings | None = None) -> AnalysisResult | None:
    initialize_database(settings)
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT payload_json FROM analyses ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        result = AnalysisResult.from_dict(json.loads(row["payload_json"]))
        action_rows = connection.execute(
            "SELECT id, status, payload_json FROM actions WHERE analysis_id = ?",
            (result.id,),
        ).fetchall()
        saved_items = {
            action_row["id"]: ActionItem.from_dict(json.loads(action_row["payload_json"]))
            for action_row in action_rows
        }
        for item in result.items:
            saved = saved_items.get(item.id)
            if saved:
                status = next(row["status"] for row in action_rows if row["id"] == item.id)
                item.status = status
                item.suggested_action = saved.suggested_action
        return result


def load_documents_for_analysis(
    result: AnalysisResult,
    settings: Settings | None = None,
) -> list[Document]:
    from app.models import Chunk

    initialize_database(settings)
    sources = sorted(result.source_names or {citation.source for item in result.items for citation in item.evidence})
    with connect(settings) as connection:
        if sources:
            placeholders = ",".join("?" for _ in sources)
            rows = connection.execute(
                f"SELECT source, content_hash, text, media_type FROM documents WHERE source IN ({placeholders})",
                sources,
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT source, content_hash, text, media_type FROM documents ORDER BY source"
            ).fetchall()
    documents: list[Document] = []
    for row in rows:
        document = Document(
            source=row["source"],
            text=row["text"],
            content_hash=row["content_hash"],
            media_type=row["media_type"],
        )
        document.chunks = [
            Chunk(chunk_id=f"{document.source}-{index:03d}", source=document.source, text=part)
            for index, part in enumerate(document.text.split("\n\n"), start=1)
            if part.strip()
        ]
        documents.append(document)
    return documents


def clear_workspace(settings: Settings | None = None) -> None:
    initialize_database(settings)
    with connect(settings) as connection:
        connection.execute("DELETE FROM actions")
        connection.execute("DELETE FROM analyses")
        connection.execute("DELETE FROM documents")
