from __future__ import annotations

from app.schemas.optimize import OptimizeRequest, OptimizeResponse
from core.optimizer_core import CodeOptimizerEngine, OptimizationRequest, OptimizationResult


class CodeOptimizer:
    def __init__(self) -> None:
        self.engine = CodeOptimizerEngine()

    def optimize(self, request: OptimizeRequest) -> OptimizeResponse:
        return to_api_response(
            self.engine.optimize(
                OptimizationRequest(
                    project_name=request.project_name,
                    project_id=request.project_id,
                    language=request.language,
                    goal=request.goal,
                    code=request.code,
                    mode=request.mode,
                )
            )
        )


def to_api_response(result: OptimizationResult) -> OptimizeResponse:
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
