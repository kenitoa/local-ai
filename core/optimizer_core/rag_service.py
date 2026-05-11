from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from core.optimizer_core.code_chunker import CodeChunk, CodeChunker
from core.optimizer_core.config import config
from core.optimizer_core.embedder import LocalEmbedder
from core.optimizer_core.rag_ranker import RagReranker, SearchQuery
from core.optimizer_core.vector_index import LocalVectorIndex, coerce_vector


COLLECTIONS = {
    "project_code_chunks",
    "optimization_knowledge",
    "past_patches",
    "error_logs",
    "benchmark_results",
}
DEFAULT_COLLECTION = "project_code_chunks"


class RagService:
    def __init__(self) -> None:
        self.index_root = Path(config.data_dir) / "indexes"
        self.chunker = CodeChunker()
        self.embedder = LocalEmbedder(
            model_path=config.embedding_model_path,
            dimension=config.embedding_dimension,
            backend=config.embedding_backend,
        )
        self.reranker = RagReranker()

    def ingest_project_files(
        self,
        project_id: str,
        project_files: list[dict[str, str]],
        collection: str = DEFAULT_COLLECTION,
    ) -> list[dict[str, str]]:
        self._validate_collection(collection)
        documents: list[dict[str, str]] = []
        for project_file in project_files:
            chunks = self.chunker.chunk_file(
                project_id=project_id,
                file_path=project_file["path"],
                content=project_file["content"],
            )
            for chunk in chunks:
                documents.append(self.add_chunk(collection, chunk))
        return documents

    def add_document(
        self,
        title: str,
        content: str,
        metadata: dict[str, object] | None = None,
        collection: str = DEFAULT_COLLECTION,
    ) -> dict[str, str]:
        self._validate_collection(collection)
        chunk = CodeChunk(
            content=content,
            metadata={
                "project_id": str((metadata or {}).get("project_id", "unknown")),
                "language": str((metadata or {}).get("language", "text")),
                "file_path": str((metadata or {}).get("path", title)),
                "symbol": title,
                "chunk_type": str((metadata or {}).get("chunk_type", "document")),
                "hash": f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
                "line_start": int((metadata or {}).get("line_start", 1)),
                "line_end": int((metadata or {}).get("line_end", max(len(content.splitlines()), 1))),
                **(metadata or {}),
            },
        )
        return self.add_chunk(collection, chunk)

    def add_chunk(self, collection: str, chunk: CodeChunk) -> dict[str, str]:
        self._validate_collection(collection)
        records = self._load_project_records(project_id_from_chunk(chunk))
        record_id = str(uuid4())
        title = f"{chunk.metadata['file_path']}::{chunk.metadata['symbol']}"
        record = {
            "id": record_id,
            "collection": collection,
            "title": title,
            "snippet": chunk.content[:500],
            "content": chunk.content,
            "metadata": chunk.metadata,
            "vector": self.embedder.embed([chunk.content])[0],
        }
        records.append(record)
        self._save_project_records(project_id_from_chunk(chunk), records[-1000:])
        return {"id": record_id, "title": title}

    def is_ready(self) -> bool:
        self.index_root.mkdir(parents=True, exist_ok=True)
        return self.index_root.exists()

    def backend_name(self) -> str:
        return f"{self.embedder.backend_name}+{LocalVectorIndex(config.embedding_dimension).backend}"

    def search(
        self,
        query: str,
        limit: int = 5,
        project_id: str | None = None,
        collection: str = DEFAULT_COLLECTION,
        target_path: str | None = None,
        symbols: set[str] | None = None,
        calls: set[str] | None = None,
    ) -> list[dict[str, object]]:
        self._validate_collection(collection)
        records = self._load_project_records(project_id) if project_id else self._load_all_records()
        records = [record for record in records if record.get("collection") == collection]
        if not records:
            return [
                {
                    "title": "local bootstrap",
                    "snippet": f"RAG index is empty. Query received: {query}",
                    "metadata": {"collection": collection, "backend": self.backend_name()},
                    "score": 0.0,
                }
            ]

        query_vector = self.embedder.embed([query])[0]
        vectors = [coerce_vector(record.get("vector", []), len(query_vector)) for record in records]
        semantic_results = LocalVectorIndex(
            config.embedding_dimension,
            self._project_index_dir(project_id) if project_id else None,
        ).search(vectors, query_vector, max(limit * 4, limit))
        semantic_scores = {item.index: item.score for item in semantic_results}
        ranked = self.reranker.rerank(
            records=records,
            dense_scores=semantic_scores,
            query=SearchQuery(
                text=query,
                target_path=target_path,
                symbols=symbols or set(),
                calls=calls or set(),
            ),
            limit=limit,
        )
        return [self._to_search_result(record, score) for _, record, score in ranked]

    def _to_search_result(self, item: dict[str, object], score) -> dict[str, object]:
        metadata = item.get("metadata", {})
        if isinstance(metadata, dict):
            metadata = {
                **metadata,
                "backend": self.backend_name(),
                "ranker": {
                    "dense_similarity": score.dense,
                    "keyword_score": score.keyword,
                    "symbol_match_score": score.symbol,
                    "call_graph_distance_score": score.call_graph,
                    "file_path_relevance_score": score.path,
                },
            }
        return {
            "id": item["id"],
            "collection": item["collection"],
            "title": item["title"],
            "snippet": item["snippet"],
            "metadata": metadata,
            "score": round(float(score.final), 4),
        }

    def _load_project_records(self, project_id: str | None) -> list[dict[str, object]]:
        if not project_id:
            return []
        path = self._project_index_dir(project_id) / "metadata.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _load_all_records(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        if not self.index_root.exists():
            return records
        for path in self.index_root.glob("*/metadata.jsonl"):
            records.extend(
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        return records

    def _save_project_records(self, project_id: str, records: list[dict[str, object]]) -> None:
        index = LocalVectorIndex(config.embedding_dimension, self._project_index_dir(project_id))
        index.save(
            records=records,
            keyword_index=build_keyword_index(records),
            symbol_graph=build_symbol_graph(records),
        )

    def _project_index_dir(self, project_id: str | None) -> Path:
        return self.index_root / safe_project_id(project_id or "global")

    def _validate_collection(self, collection: str) -> None:
        if collection not in COLLECTIONS:
            raise ValueError(f"Unsupported RAG collection: {collection}")


def project_id_from_chunk(chunk: CodeChunk) -> str:
    return safe_project_id(str(chunk.metadata.get("project_id", "unknown")))


def safe_project_id(project_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", project_id.strip())
    return cleaned or "unknown"


def build_keyword_index(records: list[dict[str, object]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for record in records:
        record_id = str(record["id"])
        text = f"{record.get('title', '')} {record.get('snippet', '')}"
        for token in sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower()))):
            index.setdefault(token, []).append(record_id)
    return index


def build_symbol_graph(records: list[dict[str, object]]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for record in records:
        metadata = record.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        symbol = str(metadata.get("symbol", "")).strip()
        if not symbol:
            continue
        calls = metadata.get("calls", [])
        imports = metadata.get("imports", [])
        edges = []
        if isinstance(calls, list):
            edges.extend(str(item) for item in calls)
        if isinstance(imports, list):
            edges.extend(str(item) for item in imports)
        graph[symbol] = sorted(set(edges))
    return graph
