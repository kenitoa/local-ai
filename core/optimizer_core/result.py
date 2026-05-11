from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OptimizeResult:
    summary: str
    risk_level: str
    bottleneck: str
    patch: str
    tests_passed: bool = False
    benchmark_before: float | None = None
    benchmark_after: float | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    explanation: str = ""
    expected_effect: str = ""
    test_command: str = ""
    benchmark_command: str = ""
    checks: list[str] = field(default_factory=list)
    rag_context: list[str] = field(default_factory=list)
    llm_backend: str = "not_used_local_algorithm"


@dataclass(slots=True)
class AnalyzeResult:
    project_id: str
    findings: list[dict[str, object]]
    rag_context: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkPlan:
    project_id: str
    requested_command: str
    checks: list[str]


@dataclass(slots=True)
class RagIngestResult:
    project_id: str
    collection: str
    documents: list[dict[str, str]]
