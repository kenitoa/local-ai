from __future__ import annotations

import ast

from core.optimizer_core.analyzer import AnalysisRuleEngine, PythonAstAnalyzer, complexity_warnings, parse_source, profile_hints
from core.optimizer_core.analyzer.models import CodeAnalysis
from core.optimizer_core.models import OptimizationRequest


class CodeAnalyzer:
    def __init__(self) -> None:
        self.ast_analyzer = PythonAstAnalyzer()
        self.rules = AnalysisRuleEngine()

    def analyze(self, request: OptimizationRequest) -> dict[str, object]:
        non_empty_lines = [line for line in request.code.splitlines() if line.strip()]
        structured = self.analyze_code(request.code, request.language)
        return {
            "project_name": request.project_name,
            "project_id": request.project_id,
            "language": request.language,
            "goal": request.goal,
            "parser_backend": structured.parser_backend,
            "parse_ok": structured.parse_ok,
            "parse_error": structured.parse_error,
            "line_count": len(request.code.splitlines()),
            "non_empty_line_count": len(non_empty_lines),
            "character_count": len(request.code),
            "functions": [item.to_dict() for item in structured.functions],
            "classes": [item.to_dict() for item in structured.classes],
            "imports": [item.to_dict() for item in structured.imports],
            "call_graph": structured.call_graph,
            "complexity_warnings": structured.complexity_warnings,
            "optimization_opportunities": [
                item.to_dict() for item in structured.optimization_opportunities
            ],
            "static_findings": structured.static_findings,
            "code_analysis": structured.to_dict(),
        }

    def analyze_code(self, code: str, language: str) -> CodeAnalysis:
        parse_result = parse_source(code, language)
        if language.lower() != "python":
            return CodeAnalysis(
                parser_backend=parse_result.backend,
                parse_ok=parse_result.ok,
                parse_error=parse_result.error,
                static_findings=[
                    {
                        "severity": "info",
                        "message": f"Static analyzer for {language} is not implemented yet.",
                        "line": 1,
                    }
                ],
            )

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return CodeAnalysis(
                parser_backend=parse_result.backend,
                parse_ok=False,
                parse_error=exc.msg,
                static_findings=[
                    {
                        "severity": "high",
                        "message": f"Python syntax error: {exc.msg}",
                        "line": exc.lineno or 1,
                    }
                ],
            )

        structured = self.ast_analyzer.analyze(code)
        warnings = [*complexity_warnings(structured.functions), *profile_hints(structured.functions)]
        opportunities = self.rules.detect(tree, structured)
        findings = self._static_findings(structured, warnings, opportunities)
        return CodeAnalysis(
            functions=structured.functions,
            classes=structured.classes,
            imports=structured.imports,
            call_graph=structured.call_graph,
            complexity_warnings=warnings,
            optimization_opportunities=opportunities,
            parser_backend=parse_result.backend,
            parse_ok=parse_result.ok,
            parse_error=parse_result.error,
            static_findings=findings,
        )

    def static_findings(self, code: str, language: str) -> list[dict[str, object]]:
        return self.analyze_code(code, language).static_findings

    def _static_findings(
        self,
        analysis: CodeAnalysis,
        warnings: list[str],
        opportunities,
    ) -> list[dict[str, object]]:
        findings: list[dict[str, object]] = []
        for warning in warnings:
            severity = "medium" if "nested loop" in warning or "complexity" in warning else "low"
            findings.append({"severity": severity, "message": warning, "line": 1})
        for opportunity in opportunities:
            findings.append(
                {
                    "severity": severity_for_risk(opportunity.risk),
                    "message": f"{opportunity.rule}: {opportunity.reason}",
                    "line": opportunity.target_line,
                    "rule": opportunity.rule,
                    "symbol": opportunity.symbol,
                }
            )
        if not findings:
            findings.append(
                {
                    "severity": "info",
                    "message": "No obvious static issue found. Use tests and benchmarks to confirm optimization value.",
                    "line": 1,
                }
            )
        return findings


def severity_for_risk(risk: str) -> str:
    return {"low": "low", "medium": "medium", "high": "high"}.get(risk, "info")
