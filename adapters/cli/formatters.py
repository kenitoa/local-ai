from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from core.optimizer_core import OptimizeResult


def result_to_json(result: OptimizeResult) -> str:
    payload: dict[str, Any]
    if is_dataclass(result):
        payload = asdict(result)
    else:
        payload = dict(result.__dict__)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def result_to_text(result: OptimizeResult, show_patch: bool = True) -> str:
    sections = [
        f"Summary: {result.summary}",
        f"Risk: {result.risk_level}",
        f"Bottleneck: {result.bottleneck}",
        f"Expected effect: {result.expected_effect}",
        f"Test command: {result.test_command}",
        f"Benchmark command: {result.benchmark_command}",
        f"Runtime: {result.llm_backend}",
    ]
    if result.checks:
        sections.append("Checks:\n" + "\n".join(f"- {item}" for item in result.checks))
    if result.notes:
        sections.append("Notes:\n" + "\n".join(f"- {item}" for item in result.notes))
    if show_patch:
        sections.append("Patch:\n" + (result.patch or "(no patch generated)"))
    return "\n\n".join(sections)


def write_patch(path: Path, patch: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(patch, encoding="utf-8")
