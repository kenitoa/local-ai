from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class FunctionInfo:
    name: str
    line_start: int
    line_end: int
    args: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    loops: int = 0
    branches: int = 0
    returns: int = 0
    max_loop_depth: int = 0
    complexity: int = 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ClassInfo:
    name: str
    line_start: int
    line_end: int
    methods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ImportInfo:
    module: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    line: int = 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OptimizationOpportunity:
    rule: str
    reason: str
    risk: str
    target_line: int
    symbol: str = ""
    category: str = "performance"
    confidence: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CodeAnalysis:
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    call_graph: dict[str, list[str]] = field(default_factory=dict)
    complexity_warnings: list[str] = field(default_factory=list)
    optimization_opportunities: list[OptimizationOpportunity] = field(default_factory=list)
    parser_backend: str = "unknown"
    parse_ok: bool = True
    parse_error: str = ""
    static_findings: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "functions": [item.to_dict() for item in self.functions],
            "classes": [item.to_dict() for item in self.classes],
            "imports": [item.to_dict() for item in self.imports],
            "call_graph": self.call_graph,
            "complexity_warnings": self.complexity_warnings,
            "optimization_opportunities": [item.to_dict() for item in self.optimization_opportunities],
            "parser_backend": self.parser_backend,
            "parse_ok": self.parse_ok,
            "parse_error": self.parse_error,
            "static_findings": self.static_findings,
        }
