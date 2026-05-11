from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.optimizer_core.config import config
from core.optimizer_core.models import OptimizationRequest, OptimizationResult


RAW_EVENTS = "optimization_events.jsonl"
HUMAN_REVIEWED = "human_reviewed.jsonl"


class TrainingDataCollector:
    def __init__(self) -> None:
        self.root = Path(config.data_dir) / "fine_tune"
        self.raw_path = self.root / RAW_EVENTS

    def collect_optimization_event(
        self,
        request: OptimizationRequest,
        response: OptimizationResult,
        static_analysis: list[dict[str, object]],
        rag_evidence: list[dict[str, object]],
        code_after: str = "",
        tests_passed: bool | None = None,
        benchmark_before: float | None = None,
        benchmark_after: float | None = None,
        human_approved: bool = False,
        human_final_patch: str = "",
    ) -> dict[str, object]:
        record = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "quality": self.grade_record(tests_passed, benchmark_before, benchmark_after, human_approved),
            "task_type": "code_optimization",
            "language": request.language,
            "user_goal": request.goal,
            "environment": {
                "device": config.ai_device,
                "os": platform.system().lower(),
                "python_version": platform.python_version(),
                "llm_backend": config.llm_backend,
            },
            "code_before": request.code,
            "context": {
                "project_id": request.project_id,
                "project_name": request.project_name,
                "related_files": self._related_files(rag_evidence),
                "static_analysis": static_analysis,
                "rag_evidence": self._compact_rag(rag_evidence),
            },
            "ideal_answer": {
                "diagnosis": response.bottleneck,
                "patch": human_final_patch or response.patch,
                "explanation": response.summary,
                "tests": response.checks,
                "risk_level": response.risk_level,
                "expected_effect": response.expected_effect,
            },
            "code_after": code_after,
            "eval": {
                "tests_passed": tests_passed,
                "benchmark_before": benchmark_before,
                "benchmark_after": benchmark_after,
                "human_approved": human_approved,
            },
            "notes": response.notes,
        }
        self.append_jsonl(self.raw_path, record)
        return record

    def grade_record(
        self,
        tests_passed: bool | None,
        benchmark_before: float | None,
        benchmark_after: float | None,
        human_approved: bool,
    ) -> str:
        improved = (
            benchmark_before is not None
            and benchmark_after is not None
            and benchmark_after < benchmark_before
        )
        if tests_passed is True and improved and human_approved:
            return "gold"
        if tests_passed is True and human_approved:
            return "silver"
        return "bronze"

    def append_jsonl(self, path: Path, record: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _related_files(self, rag_evidence: list[dict[str, object]]) -> list[str]:
        paths: list[str] = []
        for item in rag_evidence:
            metadata = item.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("file_path"):
                paths.append(str(metadata["file_path"]))
        return sorted(set(paths))

    def _compact_rag(self, rag_evidence: list[dict[str, object]]) -> list[dict[str, object]]:
        compact: list[dict[str, object]] = []
        for item in rag_evidence:
            compact.append(
                {
                    "collection": item.get("collection"),
                    "title": item.get("title"),
                    "snippet": item.get("snippet"),
                    "metadata": item.get("metadata", {}),
                    "score": item.get("score"),
                }
            )
        return compact

