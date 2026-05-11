from __future__ import annotations

from app.schemas.optimize import (
    AnalyzeRequest,
    AnalyzeResponse,
    BenchmarkRequest,
    BenchmarkResponse,
    OptimizeRequest,
    OptimizeResponse,
    PatchRequest,
)
from app.schemas.rag import RagIngestRequest, RagIngestResponse, RagSearchRequest
from app.services.job_store import JobStore
from app.services.project_store import ProjectStore
from core.optimizer_core import OptimizationResult
from core.optimizer_core.result import AnalyzeResult, OptimizeResult
from core.optimizer_core.workflows import OptimizerWorkflow


class ApiOptimizerAdapter:
    def __init__(self) -> None:
        self.workflow = OptimizerWorkflow()
        self.projects = ProjectStore()
        self.jobs = JobStore()

    def optimize(self, payload: OptimizeRequest) -> OptimizeResponse:
        result = self.workflow.optimize_code(
            project_name=payload.project_name,
            project_id=payload.project_id,
            language=payload.language,
            goal=payload.goal,
            code=payload.code,
            mode=payload.mode,
        )
        return to_api_response(result)

    def analyze_project(self, payload: AnalyzeRequest) -> AnalyzeResponse:
        files = self.projects.read_project_files(payload.project_id)
        return to_analyze_response(
            self.workflow.analyze_project_files(
                project_id=payload.project_id,
                goal=payload.goal,
                project_files=files,
            )
        )

    def create_patch(self, payload: PatchRequest) -> OptimizeResponse:
        code = payload.code
        if code is None and payload.path:
            files = self.projects.read_project_files(payload.project_id, [payload.path])
            code = files[0]["content"] if files else ""
        result = self.workflow.optimize_patch(
            project_id=payload.project_id,
            goal=payload.goal,
            language=payload.language,
            code=code or "",
            mode=payload.mode,
        )
        return to_api_response(result)

    def benchmark(self, payload: BenchmarkRequest) -> BenchmarkResponse:
        plan = self.workflow.benchmark_plan(
            project_id=payload.project_id,
            command=payload.command,
            language=payload.language,
        )
        job = self.jobs.create_job(
            kind="benchmark",
            result={
                "project_id": plan.project_id,
                "requested_command": plan.requested_command,
                "suggested_checks": plan.checks,
            },
        )
        return BenchmarkResponse(job_id=str(job["id"]), status=str(job["status"]), checks=plan.checks)

    def ingest_rag(self, payload: RagIngestRequest) -> RagIngestResponse:
        project_files = self.projects.read_project_files(payload.project_id, payload.paths)
        result = self.workflow.ingest_project_files(
            project_id=payload.project_id,
            project_files=project_files,
            collection=payload.collection,
        )
        return RagIngestResponse(
            project_id=result.project_id,
            collection=result.collection,
            indexed_count=len(result.documents),
            document_ids=[document["id"] for document in result.documents],
        )

    def search_rag(self, payload: RagSearchRequest) -> dict[str, object]:
        return {
            "matches": self.workflow.search_rag(
                query=payload.query,
                limit=payload.limit,
                project_id=payload.project_id,
                collection=payload.collection,
            )
        }


def to_analyze_response(result: AnalyzeResult) -> AnalyzeResponse:
    return AnalyzeResponse(
        project_id=result.project_id,
        findings=result.findings,
        rag_context=result.rag_context,
    )


def to_api_response(result: OptimizeResult | OptimizationResult) -> OptimizeResponse:
    return OptimizeResponse(
        summary=result.summary,
        risk_level=result.risk_level,
        bottleneck=result.bottleneck,
        explanation=result.explanation,
        patch=result.patch,
        expected_effect=result.expected_effect,
        test_command=result.test_command,
        benchmark_command=result.benchmark_command,
        checks=result.checks,
        notes=result.notes,
        rag_context=result.rag_context,
        llm_backend=result.llm_backend,
    )
