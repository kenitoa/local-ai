from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from core.optimizer_core.embedder import normalize_tokens


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    target_path: str | None = None
    symbols: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class RerankScore:
    final: float
    dense: float
    keyword: float
    symbol: float
    call_graph: float
    path: float


class RagReranker:
    def rerank(
        self,
        records: list[dict[str, object]],
        dense_scores: dict[int, float],
        query: SearchQuery,
        limit: int,
    ) -> list[tuple[int, dict[str, object], RerankScore]]:
        query_terms = set(normalize_tokens(query.text))
        scored = [
            (
                index,
                record,
                self.score(
                    record=record,
                    dense_score=dense_scores.get(index, 0.0),
                    query=query,
                    query_terms=query_terms,
                ),
            )
            for index, record in enumerate(records)
        ]
        scored.sort(key=lambda item: item[2].final, reverse=True)
        return scored[:limit]

    def score(
        self,
        record: dict[str, object],
        dense_score: float,
        query: SearchQuery,
        query_terms: set[str],
    ) -> RerankScore:
        keyword = keyword_score(record, query_terms)
        symbol = symbol_match_score(record, query)
        call_graph = call_graph_score(record, query)
        path = path_score(record, query.target_path)
        final = (
            0.35 * clamp01(dense_score)
            + 0.25 * keyword
            + 0.20 * symbol
            + 0.10 * call_graph
            + 0.10 * path
        )
        return RerankScore(
            final=round(final, 6),
            dense=round(clamp01(dense_score), 6),
            keyword=round(keyword, 6),
            symbol=round(symbol, 6),
            call_graph=round(call_graph, 6),
            path=round(path, 6),
        )


def keyword_score(record: dict[str, object], query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    body = f"{record.get('title', '')} {record.get('content', '')}".lower()
    body_terms = set(normalize_tokens(body))
    return len(query_terms & body_terms) / max(len(query_terms), 1)


def symbol_match_score(record: dict[str, object], query: SearchQuery) -> float:
    metadata = metadata_dict(record)
    symbol = str(metadata.get("symbol", "")).lower()
    title = str(record.get("title", "")).lower()
    if not query.symbols:
        query_terms = set(normalize_tokens(query.text))
        if symbol and symbol.lower() in query_terms:
            return 1.0
        return 0.0
    normalized_symbols = {item.lower() for item in query.symbols}
    if symbol.lower() in normalized_symbols:
        return 1.0
    if any(item in title for item in normalized_symbols):
        return 0.7
    return 0.0


def call_graph_score(record: dict[str, object], query: SearchQuery) -> float:
    metadata = metadata_dict(record)
    calls = metadata.get("calls", [])
    imports = metadata.get("imports", [])
    if not isinstance(calls, list):
        calls = []
    if not isinstance(imports, list):
        imports = []
    query_calls = {item.lower() for item in query.calls}
    if not query_calls:
        query_calls = set(normalize_tokens(query.text))
    record_calls = {str(item).lower() for item in [*calls, *imports]}
    if not query_calls or not record_calls:
        return 0.0
    return len(query_calls & record_calls) / max(len(query_calls), 1)


def path_score(record: dict[str, object], target_path: str | None) -> float:
    if not target_path:
        return 0.0
    metadata = metadata_dict(record)
    candidate = str(metadata.get("file_path", ""))
    if not candidate:
        return 0.0
    target = normalize_path(target_path)
    candidate_path = normalize_path(candidate)
    if candidate_path == target:
        return 1.0
    target_parts = set(PurePosixPath(target).parts)
    candidate_parts = set(PurePosixPath(candidate_path).parts)
    if not target_parts:
        return 0.0
    return len(target_parts & candidate_parts) / len(target_parts)


def metadata_dict(record: dict[str, object]) -> dict[str, object]:
    metadata = record.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
