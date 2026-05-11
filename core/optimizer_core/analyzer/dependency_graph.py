from __future__ import annotations

from core.optimizer_core.analyzer.models import FunctionInfo


def build_call_graph(functions: list[FunctionInfo]) -> dict[str, list[str]]:
    known = {function.name for function in functions}
    graph: dict[str, list[str]] = {}
    for function in functions:
        graph[function.name] = sorted({call for call in function.calls if call in known or "." in call})
    return graph
