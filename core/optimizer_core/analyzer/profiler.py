from __future__ import annotations

from core.optimizer_core.analyzer.models import FunctionInfo


def profile_hints(functions: list[FunctionInfo]) -> list[str]:
    hints: list[str] = []
    for function in functions:
        if function.loops:
            hints.append(f"{function.name}: benchmark loop body before changing data structures.")
        if len(function.calls) >= 8:
            hints.append(f"{function.name}: repeated calls may benefit from local binding or caching.")
    return hints
