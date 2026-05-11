from __future__ import annotations

from dataclasses import dataclass, field

from core.optimizer_core.result import OptimizeResult


@dataclass(slots=True)
class OptimizationRequest:
    code: str
    project_name: str = "local-upload"
    project_id: str | None = None
    language: str = "python"
    goal: str = "Improve performance while preserving behavior."
    mode: str = "hybrid"


OptimizationResult = OptimizeResult


@dataclass(slots=True)
class OptimizationCandidate:
    rule_id: str
    title: str
    summary: str
    bottleneck: str
    patch: str
    updated_code: str
    risk_level: str
    expected_effect: str
    score: float
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateVerification:
    candidate: OptimizationCandidate
    ok: bool
    score: float
    notes: list[str] = field(default_factory=list)
