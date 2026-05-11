from __future__ import annotations

from core.optimizer_core.code_analyzer import CodeAnalyzer
from core.optimizer_core.engine import CodeOptimizerEngine
from core.optimizer_core.eval_service import EvalService
from core.optimizer_core.models import OptimizationRequest
from core.optimizer_core.rag_service import DEFAULT_COLLECTION, RagService
from core.optimizer_core.result import AnalyzeResult, BenchmarkPlan, OptimizeResult, RagIngestResult


class OptimizerWorkflow:
    def __init__(self) -> None:
        self.engine = CodeOptimizerEngine()
        self.analyzer = CodeAnalyzer()
        self.rag = RagService()
        self.eval = EvalService()

    def optimize_code(
        self,
        project_name: str,
        project_id: str | None,
        language: str,
        goal: str,
        code: str,
        mode: str = "hybrid",
    ) -> OptimizeResult:
        return self.engine.optimize(
            OptimizationRequest(
                project_name=project_name,
                project_id=project_id,
                language=language,
                goal=goal,
                code=code,
                mode=mode,
            )
        )

    def analyze_project_files(
        self,
        project_id: str,
        goal: str,
        project_files: list[dict[str, str]],
    ) -> AnalyzeResult:
        findings = [
            {
                "path": project_file["path"],
                **self.analyzer.analyze(
                    OptimizationRequest(
                        project_id=project_id,
                        project_name=project_id,
                        language=guess_language(project_file["path"]),
                        goal=goal,
                        code=project_file["content"],
                    )
                ),
            }
            for project_file in project_files
        ]
        context = self.rag.search(goal, limit=5, project_id=project_id)
        return AnalyzeResult(
            project_id=project_id,
            findings=findings,
            rag_context=[str(item["snippet"]) for item in context],
        )

    def optimize_patch(
        self,
        project_id: str,
        goal: str,
        language: str,
        code: str,
        mode: str = "hybrid",
    ) -> OptimizeResult:
        return self.engine.optimize(
            OptimizationRequest(
                project_id=project_id,
                project_name=project_id,
                language=language,
                goal=goal,
                code=code,
                mode=mode,
            )
        )

    def benchmark_plan(
        self,
        project_id: str,
        command: str,
        language: str,
    ) -> BenchmarkPlan:
        return BenchmarkPlan(
            project_id=project_id,
            requested_command=command,
            checks=self.eval.suggested_checks(language),
        )

    def ingest_project_files(
        self,
        project_id: str,
        project_files: list[dict[str, str]],
        collection: str = DEFAULT_COLLECTION,
    ) -> RagIngestResult:
        documents = self.rag.ingest_project_files(
            project_id=project_id,
            project_files=project_files,
            collection=collection,
        )
        return RagIngestResult(project_id=project_id, collection=collection, documents=documents)

    def search_rag(
        self,
        query: str,
        limit: int,
        project_id: str | None,
        collection: str = DEFAULT_COLLECTION,
    ) -> list[dict[str, object]]:
        return self.rag.search(
            query=query,
            limit=limit,
            project_id=project_id,
            collection=collection,
        )


def guess_language(path: str) -> str:
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "java": "java",
    }.get(suffix, "text")
