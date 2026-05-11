from __future__ import annotations

import json
import platform
import re

from core.optimizer_core.config import config
from core.optimizer_core.exceptions import UnsupportedOptimizationMode
from core.optimizer_core.models import CandidateVerification, OptimizationRequest, OptimizationResult
from core.optimizer_core.code_analyzer import CodeAnalyzer
from core.optimizer_core.eval_service import EvalService
from core.optimizer_core.local_model_runtime import get_local_model_runtime
from core.optimizer_core.patch_service import PatchService
from core.optimizer_core.rag_service import RagService
from core.optimizer_core.request import OptimizeRequest
from core.optimizer_core.rules import RuleBasedOptimizer
from core.optimizer_core.training_data import TrainingDataCollector
from core.optimizer_core.verifier import CandidateVerifier


class CodeOptimizerEngine:
    def __init__(self) -> None:
        self.analyzer = CodeAnalyzer()
        self.rag = RagService()
        self.model = get_local_model_runtime()
        self.eval = EvalService()
        self.patch = PatchService()
        self.rules = RuleBasedOptimizer()
        self.verifier = CandidateVerifier()
        self.training = TrainingDataCollector()

    def optimize(self, request: OptimizationRequest | OptimizeRequest) -> OptimizationResult:
        if isinstance(request, OptimizeRequest):
            request = self._from_project_request(request)
        if request.mode not in {"deterministic", "local_llm", "hybrid"}:
            raise UnsupportedOptimizationMode(f"Unsupported optimization mode: {request.mode}")
        if request.mode == "deterministic":
            return self.optimize_with_rules_only(request)
        if request.mode == "local_llm":
            return self.optimize_with_local_llm(request)
        return self.optimize_with_rules_and_llm(request)

    def optimize_with_rules_only(self, request: OptimizationRequest) -> OptimizationResult:
        analysis = self.analyzer.analyze(request)
        static_findings = analysis["static_findings"]
        context: list[dict[str, object]] = []
        candidates = self.rules.generate_candidates(request, analysis, context)
        verified = self.verifier.verify(request, candidates)
        self._record_uploaded_code(request)
        best_local = self._select_local_candidate(verified)
        if best_local is not None:
            response = self._candidate_response(request, best_local, context, verified)
            self.training.collect_optimization_event(
                request=request,
                response=response,
                static_analysis=static_findings,
                rag_evidence=context,
            )
            return response

        local_plan = self._local_plan(request, static_findings, verified)
        response = OptimizationResult(
            summary=local_plan["summary"],
            risk_level=local_plan["risk_level"],
            bottleneck=local_plan["bottleneck"],
            explanation=local_plan["summary"],
            patch="",
            expected_effect=local_plan["expected_effect"],
            test_command=self.eval.test_command(request.language),
            benchmark_command=self.eval.benchmark_command(request.language),
            checks=self.eval.suggested_checks(request.language),
            notes=[
                *local_plan["notes"],
                "Mode deterministic: local model patch assistant was not called.",
            ],
            rag_context=[str(item["snippet"]) for item in context],
            llm_backend="not_used_deterministic",
        )
        self.training.collect_optimization_event(
            request=request,
            response=response,
            static_analysis=static_findings,
            rag_evidence=context,
        )
        return response

    def optimize_with_local_llm(self, request: OptimizationRequest) -> OptimizationResult:
        analysis = self.analyzer.analyze(request)
        target_summary = self._target_summary(request)
        static_findings = analysis["static_findings"]
        context = self._search_context(request, static_findings)
        self._record_uploaded_code(request)
        local_plan = self._local_plan(request, static_findings, [])
        patch_assist = self._request_patch_assist(request, analysis, target_summary, context, [], local_plan)
        patch = self._normalize_patch(request, patch_assist.get("patch", ""))
        notes = [
            *local_plan["notes"],
            "Mode local_llm: no local rewrite candidate was selected before patch drafting.",
            *patch_assist.get("notes", []),
            *[f"Edge case: {item}" for item in patch_assist.get("edge_cases", [])],
        ]
        if patch_assist.get("patch") and not patch:
            notes.append("Local verifier rejected the model-drafted patch.")
        response = OptimizationResult(
            summary=local_plan["summary"],
            risk_level=local_plan["risk_level"],
            bottleneck=local_plan["bottleneck"],
            explanation=patch_assist.get("explanation", local_plan["summary"]),
            patch=patch,
            expected_effect=local_plan["expected_effect"],
            test_command=self.eval.test_command(request.language),
            benchmark_command=self.eval.benchmark_command(request.language),
            checks=self.eval.suggested_checks(request.language),
            notes=notes,
            rag_context=[str(item["snippet"]) for item in context],
            llm_backend=patch_assist["backend"],
        )
        self.training.collect_optimization_event(
            request=request,
            response=response,
            static_analysis=static_findings,
            rag_evidence=context,
        )
        return response

    def optimize_with_rules_and_llm(self, request: OptimizationRequest) -> OptimizationResult:
        analysis = self.analyzer.analyze(request)
        target_summary = self._target_summary(request)
        static_findings = analysis["static_findings"]
        context = self._search_context(request, static_findings)
        candidates = self.rules.generate_candidates(request, analysis, context)
        verified = self.verifier.verify(request, candidates)
        self._record_uploaded_code(request)
        best_local = self._select_local_candidate(verified)
        if best_local is not None:
            response = self._candidate_response(request, best_local, context, verified)
            self.training.collect_optimization_event(
                request=request,
                response=response,
                static_analysis=static_findings,
                rag_evidence=context,
            )
            return response

        local_plan = self._local_plan(request, static_findings, verified)
        patch_assist = self._request_patch_assist(request, analysis, target_summary, context, verified, local_plan)
        patch = self._normalize_patch(request, patch_assist.get("patch", ""))
        notes = [
            *local_plan["notes"],
            *patch_assist.get("notes", []),
            *[f"Edge case: {item}" for item in patch_assist.get("edge_cases", [])],
        ]
        if patch_assist.get("patch") and not patch:
            notes.append("Local verifier rejected the model-drafted patch.")
        response = OptimizationResult(
            summary=local_plan["summary"],
            risk_level=local_plan["risk_level"],
            bottleneck=local_plan["bottleneck"],
            explanation=patch_assist.get("explanation", local_plan["summary"]),
            patch=patch,
            expected_effect=local_plan["expected_effect"],
            test_command=self.eval.test_command(request.language),
            benchmark_command=self.eval.benchmark_command(request.language),
            checks=self.eval.suggested_checks(request.language),
            notes=notes,
            rag_context=[str(item["snippet"]) for item in context],
            llm_backend=patch_assist["backend"],
        )
        self.training.collect_optimization_event(
            request=request,
            response=response,
            static_analysis=static_findings,
            rag_evidence=context,
        )
        return response

    def _from_project_request(self, request: OptimizeRequest) -> OptimizationRequest:
        if request.mode not in {"deterministic", "local_llm", "hybrid"}:
            raise UnsupportedOptimizationMode(f"Unsupported optimization mode: {request.mode}")
        return OptimizationRequest(
            code=request.read_target_code(),
            project_name=request.primary_target,
            project_id=request.project_id,
            language=request.language,
            goal=request.user_goal,
            mode=request.mode,
        )

    def _record_uploaded_code(self, request: OptimizationRequest) -> None:
        self.rag.add_document(
            title=f"{request.project_name}:{request.language}",
            content=request.code,
            metadata={
                "kind": "uploaded-code",
                "goal": request.goal,
                "project_id": request.project_id or request.project_name,
                "language": request.language,
                "chunk_type": "uploaded_code",
            },
        )

    def _target_summary(self, request: OptimizationRequest) -> dict[str, object]:
        return {
            "project_id": request.project_id,
            "project_name": request.project_name,
            "language": request.language,
            "goal": request.goal,
            "line_count": len(request.code.splitlines()),
            "has_tests_hint": "test" in request.code.lower() or "pytest" in request.code.lower(),
        }

    def _search_context(
        self,
        request: OptimizationRequest,
        static_findings: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        query_parts = [
            request.language,
            request.goal,
            " ".join(str(item["message"]) for item in static_findings[:3]),
        ]
        project_id = request.project_id or request.project_name
        results = self.rag.search(
            query=" ".join(query_parts),
            limit=6,
            project_id=project_id,
            collection="project_code_chunks",
            target_path=self._target_path(request),
            symbols=self._query_symbols(request),
            calls=self._query_calls(static_findings),
        )
        knowledge = self.rag.search(
            query=f"{request.language} optimization benchmark unified diff",
            limit=3,
            project_id=None,
            collection="optimization_knowledge",
        )
        return results + knowledge

    def _target_path(self, request: OptimizationRequest) -> str | None:
        if request.project_name and "/" in request.project_name:
            return request.project_name
        return None

    def _query_symbols(self, request: OptimizationRequest) -> set[str]:
        return {
            match
            for match in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", request.goal)
            if "_" in match or match[:1].isupper()
        }

    def _query_calls(self, static_findings: list[dict[str, object]]) -> set[str]:
        calls: set[str] = set()
        for finding in static_findings:
            message = str(finding.get("message", ""))
            calls.update(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?\b", message))
        return calls

    def _build_patch_assist_prompt(
        self,
        request: OptimizationRequest,
        analysis: dict[str, object],
        target_summary: dict[str, object],
        context: list[dict[str, object]],
        verified_candidates: list[CandidateVerification],
        local_plan: dict[str, object],
    ) -> str:
        context_summary = [
            {
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "metadata": item.get("metadata", {}),
            }
            for item in context
        ]
        payload = {
            "user_request": request.goal,
            "target_code": request.code,
            "target_summary": target_summary,
            "related_file_summary": context_summary,
            "rag_results": context_summary,
            "static_analysis": analysis["static_findings"],
            "structured_code_analysis": analysis.get("code_analysis", {}),
            "local_algorithm_decision": {
                "summary": local_plan["summary"],
                "risk_level": local_plan["risk_level"],
                "bottleneck": local_plan["bottleneck"],
                "expected_effect": local_plan["expected_effect"],
                "selected_rule": local_plan["selected_rule"],
                "test_command": self.eval.test_command(request.language),
                "benchmark_command": self.eval.benchmark_command(request.language),
            },
            "local_algorithm_candidates": [
                {
                    "rule_id": item.candidate.rule_id,
                    "title": item.candidate.title,
                    "ok": item.ok,
                    "score": round(item.score, 3),
                    "notes": item.notes,
                }
                for item in verified_candidates
            ],
            "runtime_environment": {
                "ai_device": config.ai_device,
                "local_model_runtime": config.llm_backend,
                "os": platform.system(),
                "python": platform.python_version(),
            },
            "output_schema": {
                "patch": "unified diff only, or empty string if a safe patch cannot be drafted",
                "explanation": "short explanation of the patch draft only",
                "edge_cases": ["edge cases the local verifier should consider"],
            },
        }
        return (
            "You are only a patch drafting assistant. Do not choose the bottleneck, risk level, tests, "
            "benchmark, or final recommendation; those are fixed by local_algorithm_decision. "
            "Return only valid JSON matching output_schema. The patch must be a unified diff and must "
            "target only the provided code. If unsure, return an empty patch.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    def _request_patch_assist(
        self,
        request: OptimizationRequest,
        analysis: dict[str, object],
        target_summary: dict[str, object],
        context: list[dict[str, object]],
        verified_candidates: list[CandidateVerification],
        local_plan: dict[str, object],
    ) -> dict[str, object]:
        prompt = self._build_patch_assist_prompt(
            request=request,
            analysis=analysis,
            target_summary=target_summary,
            context=context,
            verified_candidates=verified_candidates,
            local_plan=local_plan,
        )
        try:
            raw = self.model.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return only JSON. No markdown fences. You are not allowed to decide risk, "
                            "bottleneck, tests, benchmark commands, or final ranking."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1400,
            )
            parsed = self._parse_json(raw)
            return self._patch_assist_defaults(parsed, self.model.backend_name)
        except Exception as exc:
            return {
                "backend": "not_available",
                "patch": "",
                "explanation": str(local_plan["summary"]),
                "edge_cases": [],
                "notes": [f"Local model patch assistant unavailable: {exc}"],
            }

    def _parse_json(self, raw: str) -> dict[str, object]:
        trimmed = raw.strip()
        if trimmed.startswith("```"):
            trimmed = trimmed.strip("`")
            if trimmed.startswith("json"):
                trimmed = trimmed[4:].strip()
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start >= 0 and end >= start:
            trimmed = trimmed[start : end + 1]
        data = json.loads(trimmed)
        if not isinstance(data, dict):
            raise ValueError("Patch assistant response must be a JSON object.")
        return data

    def _patch_assist_defaults(
        self,
        data: dict[str, object],
        backend: str,
    ) -> dict[str, object]:
        edge_cases = data.get("edge_cases", [])
        if isinstance(edge_cases, str):
            edge_cases = [edge_cases]
        return {
            "backend": backend,
            "patch": str(data.get("patch", "")),
            "explanation": str(data.get("explanation", "Patch draft generated by local model assistant.")),
            "edge_cases": [str(item) for item in edge_cases],
            "notes": ["Local model was used only to draft patch text and explanation."],
        }

    def _normalize_patch(self, request: OptimizationRequest, patch: str) -> str:
        if not patch.strip():
            return ""
        if self.patch.is_unified_diff(patch):
            if request.language.lower() != "python":
                return patch
            updated = self.patch.apply_patch(request.code, patch)
            if updated is None:
                return ""
            try:
                import ast

                ast.parse(updated)
            except SyntaxError:
                return ""
            return patch
        return ""

    def _local_plan(
        self,
        request: OptimizationRequest,
        static_findings: list[dict[str, object]],
        verified: list[CandidateVerification],
    ) -> dict[str, object]:
        evidence = verified[0] if verified else None
        candidate = evidence.candidate if evidence else None
        first_finding = static_findings[0]["message"] if static_findings else "No static bottleneck found."
        if candidate is not None:
            return {
                "summary": candidate.summary,
                "risk_level": candidate.risk_level,
                "bottleneck": candidate.bottleneck,
                "expected_effect": candidate.expected_effect,
                "selected_rule": candidate.rule_id,
                "notes": [
                    "Local analyzer selected the optimization target and risk level.",
                    f"Local candidate score: {evidence.score:.2f}.",
                    *evidence.notes,
                ],
            }
        return {
            "summary": "Local analysis found no safe automatic rewrite candidate.",
            "risk_level": "medium",
            "bottleneck": str(first_finding),
            "expected_effect": "Manual review, tests, and benchmarks are required before changing code.",
            "selected_rule": "NO_SAFE_LOCAL_RULE",
            "notes": ["Local analyzer did not delegate optimization judgment to the model."],
        }

    def _select_local_candidate(
        self,
        verified: list[CandidateVerification],
    ) -> CandidateVerification | None:
        for item in verified:
            if item.ok and item.candidate.patch.strip() and item.score >= 0.6:
                return item
        return None

    def _candidate_response(
        self,
        request: OptimizationRequest,
        selected: CandidateVerification,
        context: list[dict[str, object]],
        verified: list[CandidateVerification],
    ) -> OptimizationResult:
        candidate = selected.candidate
        checks = self.eval.suggested_checks(request.language)
        rejected = [item for item in verified if item is not selected]
        notes = [
            *candidate.notes,
            *selected.notes,
            f"Local algorithm selected {candidate.rule_id} with score {selected.score:.2f}.",
        ]
        if request.mode == "deterministic":
            notes.append("Mode deterministic: local model patch assistant was not called.")
        if rejected:
            notes.append(f"{len(rejected)} lower-ranked local candidate(s) were not selected.")
        return OptimizationResult(
            summary=candidate.summary,
            risk_level=candidate.risk_level,
            bottleneck=candidate.bottleneck,
            explanation=candidate.summary,
            patch=candidate.patch,
            tests_passed=False,
            benchmark_before=None,
            benchmark_after=None,
            confidence=round(selected.score, 4),
            expected_effect=candidate.expected_effect,
            test_command=self.eval.test_command(request.language),
            benchmark_command=self.eval.benchmark_command(request.language),
            checks=checks,
            notes=notes,
            rag_context=[str(item["snippet"]) for item in context],
            llm_backend="not_used_deterministic" if request.mode == "deterministic" else "not_used_local_algorithm",
        )

