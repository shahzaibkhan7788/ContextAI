from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

from app.models import Chunk

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9'-]{1,}", re.IGNORECASE)
STOP_WORDS = {
    "about", "after", "again", "also", "amount", "been", "being", "between",
    "could", "from", "have", "into", "invoice", "more", "need", "please",
    "should", "that", "their", "there", "these", "this", "those", "under",
    "were", "what", "when", "where", "which", "while", "with", "would",
}


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text) if token.lower() not in STOP_WORDS]


class LocalRetriever:
    """Local evidence search with a zero-install BM25 fallback and optional FAISS vectors."""

    def __init__(self, chunks: Sequence[Chunk], model_name: str, use_faiss: bool = False):
        self.chunks = list(chunks)
        self.model_name = model_name
        self._faiss_index = None
        self._encoder = None
        self._faiss = None
        self._vectors: list[list[float]] = []
        self._tokens = [_tokens(chunk.text) for chunk in self.chunks]
        self._document_frequency: Counter[str] = Counter()
        for words in self._tokens:
            self._document_frequency.update(set(words))

        if use_faiss and self.chunks:
            self._initialize_faiss()

    @property
    def mode(self) -> str:
        return "FAISS + sentence-transformers" if self._faiss_index is not None else "local BM25"

    def _initialize_faiss(self) -> None:
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "FAISS retrieval was enabled but its optional dependencies are missing. "
                "Install them with `python -m pip install -r requirements-rag.txt`."
            ) from exc

        import numpy as np

        self._faiss = faiss
        self._encoder = SentenceTransformer(self.model_name)
        vectors = self._encoder.encode(
            [chunk.text for chunk in self.chunks],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors, dtype="float32")
        self._faiss_index = faiss.IndexFlatIP(vectors.shape[1])
        self._faiss_index.add(vectors)

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        if not self.chunks or not query.strip():
            return []
        limit = max(1, min(top_k, len(self.chunks)))
        if self._faiss_index is not None:
            vector = self._encoder.encode(
                [query],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            _, indices = self._faiss_index.search(vector.astype("float32"), limit)
            return [self.chunks[int(index)] for index in indices[0] if index >= 0]

        query_terms = _tokens(query)
        scores: list[tuple[float, int]] = []
        total = len(self.chunks)
        for index, document_terms in enumerate(self._tokens):
            term_counts = Counter(document_terms)
            length_normalizer = 1.5 * (1 - 0.75 + 0.75 * len(document_terms) / 160)
            score = 0.0
            for term in query_terms:
                frequency = term_counts[term]
                if not frequency:
                    continue
                inverse_frequency = math.log(1 + (total - self._document_frequency[term] + 0.5) /
                                             (self._document_frequency[term] + 0.5))
                score += inverse_frequency * (frequency * 2.5) / (frequency + length_normalizer)
            if score:
                scores.append((score, index))

        scores.sort(key=lambda entry: (-entry[0], entry[1]))
        return [self.chunks[index] for _, index in scores[:limit]]
