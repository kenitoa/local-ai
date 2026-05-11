from __future__ import annotations

import hashlib
import math
from typing import Any


class LocalEmbedder:
    def __init__(
        self,
        model_path: str,
        dimension: int = 384,
        backend: str = "sentence_transformers",
    ) -> None:
        self.model_path = model_path
        self.dimension = dimension
        self.requested_backend = backend
        self._model: Any | None = None
        self._backend_name: str | None = None

    @property
    def backend_name(self) -> str:
        self._ensure_backend()
        return self._backend_name or "hash"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.requested_backend == "hash":
            self._backend_name = "hash"
            return [hash_embed(text, self.dimension) for text in texts]
        try:
            model = self._sentence_transformer()
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return [[float(value) for value in vector] for vector in vectors]
        except Exception:
            self._backend_name = "hash"
            return [hash_embed(text, self.dimension) for text in texts]

    def _ensure_backend(self) -> None:
        if self._backend_name is not None:
            return
        if self.requested_backend == "hash":
            self._backend_name = "hash"
            return
        try:
            self._sentence_transformer()
            self._backend_name = "sentence_transformers"
        except Exception:
            self._backend_name = "hash"

    def _sentence_transformer(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is not installed.") from exc
        self._model = SentenceTransformer(self.model_path)
        self._backend_name = "sentence_transformers"
        return self._model


def hash_embed(text: str, dimension: int) -> list[float]:
    vector = [0.0] * dimension
    tokens = [token for token in normalize_tokens(text) if token]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = -1.0 if digest[4] % 2 else 1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def normalize_tokens(text: str) -> list[str]:
    normalized = []
    current = []
    for char in text.lower():
        if char.isalnum() or char in {"_", "."}:
            current.append(char)
            continue
        if current:
            normalized.append("".join(current))
            current = []
    if current:
        normalized.append("".join(current))
    return normalized
