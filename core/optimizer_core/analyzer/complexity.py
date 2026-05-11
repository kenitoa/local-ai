from __future__ import annotations

from core.optimizer_core.analyzer.models import FunctionInfo


def complexity_warnings(functions: list[FunctionInfo]) -> list[str]:
    warnings: list[str] = []
    for function in functions:
        if function.complexity >= 12:
            warnings.append(
                f"{function.name}: cyclomatic complexity {function.complexity}; split decision-heavy paths."
            )
        if function.max_loop_depth >= 2:
            warnings.append(f"{function.name}: nested loop depth {function.max_loop_depth}; check algorithmic cost.")
        if function.line_end - function.line_start + 1 > 80:
            warnings.append(f"{function.name}: large function; isolate the hot path before rewriting.")
    return warnings
