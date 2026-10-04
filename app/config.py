from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    embedding_model: str
    use_faiss: bool
    data_dir: Path
    database_path: Path
    demo_mode: bool = False
    require_llm: bool = False
    demo_username: str = ""
    demo_password: str = ""

    @classmethod
    def load(cls, secrets: Mapping[str, Any] | None = None) -> "Settings":
        def setting(name: str, default: str) -> str:
            value = os.getenv(name)
            if value:
                return value.strip()
            secret = secrets.get(name) if secrets else None
            return str(secret).strip() if secret is not None else default

        data_dir = Path(setting("CONTEXTFLOW_DATA_DIR", str(PROJECT_ROOT / ".contextflow")))
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        demo_mode = setting("CONTEXTFLOW_DEMO_MODE", "false").lower() in {"1", "true", "yes"}
        return cls(
            llm_base_url=setting("LLM_BASE_URL", "").rstrip("/"),
            llm_api_key=setting("LLM_API_KEY", ""),
            llm_model=setting("LLM_MODEL", "gpt-4o-mini"),
            embedding_model=setting("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            use_faiss=setting("CONTEXTFLOW_USE_FAISS", "false").lower() in {"1", "true", "yes"},
            data_dir=data_dir,
            database_path=data_dir / "contextflow.sqlite3",
            demo_mode=demo_mode,
            require_llm=demo_mode or setting("CONTEXTFLOW_REQUIRE_LLM", "false").lower() in {"1", "true", "yes"},
            demo_username=setting("DEMO_USERNAME", ""),
            demo_password=setting("DEMO_PASSWORD", ""),
        )
