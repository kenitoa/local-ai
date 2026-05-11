from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    index: int
    score: float


class LocalVectorIndex:
    def __init__(self, dimension: int, index_dir: Path | None = None) -> None:
        self.dimension = dimension
        self.backend = "faiss" if faiss_available() else "python"
        self.index_dir = index_dir

    def search(self, vectors: list[list[float]], query: list[float], limit: int) -> list[VectorSearchResult]:
        if not vectors or limit <= 0:
            return []
        if self.backend == "faiss":
            if self.index_dir is not None and (self.index_dir / "faiss.index").exists():
                return self._search_saved_faiss(query, min(limit, len(vectors)))
            return self._search_faiss(vectors, query, limit)
        return self._search_python(vectors, query, limit)

    def save(
        self,
        records: list[dict[str, Any]],
        keyword_index: dict[str, list[str]],
        symbol_graph: dict[str, list[str]],
    ) -> None:
        if self.index_dir is None:
            return
        self.index_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = self.index_dir / "metadata.jsonl"
        metadata_path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + ("\n" if records else ""),
            encoding="utf-8",
        )
        (self.index_dir / "keyword_index.pkl").write_bytes(pickle.dumps(keyword_index))
        (self.index_dir / "symbol_graph.json").write_text(
            json.dumps(symbol_graph, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self.backend == "faiss":
            self._save_faiss([coerce_vector(record.get("vector"), self.dimension) for record in records])
        else:
            (self.index_dir / "faiss.index").write_text(
                "FAISS is not installed; Python cosine search is used at runtime.\n",
                encoding="utf-8",
            )

    def _save_faiss(self, vectors: list[list[float]]) -> None:
        if self.index_dir is None:
            return
        import faiss
        import numpy as np

        index = faiss.IndexFlatIP(self.dimension)
        if vectors:
            matrix = np.asarray(vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index.add(matrix)
        faiss.write_index(index, str(self.index_dir / "faiss.index"))

    def _search_faiss(
        self,
        vectors: list[list[float]],
        query: list[float],
        limit: int,
    ) -> list[VectorSearchResult]:
        import faiss
        import numpy as np

        matrix = np.asarray(vectors, dtype="float32")
        query_matrix = np.asarray([query], dtype="float32")
        faiss.normalize_L2(matrix)
        faiss.normalize_L2(query_matrix)
        index = faiss.IndexFlatIP(self.dimension)
        index.add(matrix)
        scores, ids = index.search(query_matrix, min(limit, len(vectors)))
        return [
            VectorSearchResult(index=int(item_id), score=float(score))
            for item_id, score in zip(ids[0], scores[0])
            if int(item_id) >= 0
        ]

    def _search_saved_faiss(self, query: list[float], limit: int) -> list[VectorSearchResult]:
        import faiss
        import numpy as np

        index = faiss.read_index(str(self.index_dir / "faiss.index"))
        query_matrix = np.asarray([query], dtype="float32")
        faiss.normalize_L2(query_matrix)
        scores, ids = index.search(query_matrix, limit)
        return [
            VectorSearchResult(index=int(item_id), score=float(score))
            for item_id, score in zip(ids[0], scores[0])
            if int(item_id) >= 0
        ]

    def _search_python(
        self,
        vectors: list[list[float]],
        query: list[float],
        limit: int,
    ) -> list[VectorSearchResult]:
        ranked = [
            VectorSearchResult(index=index, score=cosine_similarity(query, vector))
            for index, vector in enumerate(vectors)
        ]
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:limit]


def faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return True


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def coerce_vector(value: Any, dimension: int) -> list[float]:
    if not isinstance(value, list):
        return [0.0] * dimension
    vector = [float(item) for item in value[:dimension]]
    if len(vector) < dimension:
        vector.extend([0.0] * (dimension - len(vector)))
    return vector
