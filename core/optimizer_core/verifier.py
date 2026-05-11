from __future__ import annotations

import ast

from core.optimizer_core.models import CandidateVerification, OptimizationCandidate, OptimizationRequest
from core.optimizer_core.patch_service import PatchService


class CandidateVerifier:
    def __init__(self) -> None:
        self.patch = PatchService()

    def verify(
        self,
        request: OptimizationRequest,
        candidates: list[OptimizationCandidate],
    ) -> list[CandidateVerification]:
        verified = [self.verify_one(request, candidate) for candidate in candidates]
        verified.sort(key=lambda item: item.score, reverse=True)
        return verified

    def verify_one(
        self,
        request: OptimizationRequest,
        candidate: OptimizationCandidate,
    ) -> CandidateVerification:
        notes: list[str] = []
        score = candidate.score

        if not candidate.patch.strip():
            notes.append("No patch was produced; kept as analysis-only evidence.")
            return CandidateVerification(candidate=candidate, ok=False, score=score, notes=notes)

        if not self.patch.is_unified_diff(candidate.patch):
            notes.append("Patch is not a unified diff.")
            return CandidateVerification(candidate=candidate, ok=False, score=score * 0.2, notes=notes)

        if request.language.lower() == "python":
            syntax_ok, syntax_note = self._python_syntax_ok(candidate.updated_code)
            if not syntax_ok:
                notes.append(syntax_note)
                return CandidateVerification(candidate=candidate, ok=False, score=score * 0.1, notes=notes)
            notes.append("Updated Python code parses successfully.")

            if self._public_symbols(request.code) != self._public_symbols(candidate.updated_code):
                notes.append("Public function/class symbols changed.")
                return CandidateVerification(candidate=candidate, ok=False, score=score * 0.25, notes=notes)
            notes.append("Public function/class symbols are preserved.")

        if candidate.risk_level == "high":
            score *= 0.4
            notes.append("High-risk candidate was down-ranked.")

        return CandidateVerification(candidate=candidate, ok=True, score=score, notes=notes)

    def _python_syntax_ok(self, code: str) -> tuple[bool, str]:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return False, f"Python syntax failed: {exc.msg}"
        return True, "ok"

    def _public_symbols(self, code: str) -> list[tuple[str, str]]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        symbols: list[tuple[str, str]] = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                symbols.append(("function", node.name))
            elif isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
                symbols.append(("async_function", node.name))
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                symbols.append(("class", node.name))
        return symbols
