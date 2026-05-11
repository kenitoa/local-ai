from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from adapters.api_optional.service import ApiOptimizerAdapter
from app.schemas.optimize import (
    AnalyzeRequest,
    AnalyzeResponse,
    BenchmarkRequest,
    BenchmarkResponse,
    OptimizeRequest,
    OptimizeResponse,
    PatchRequest,
)

router = APIRouter()


@router.post("/", response_model=OptimizeResponse)
def optimize_code(payload: OptimizeRequest) -> OptimizeResponse:
    return get_adapter().optimize(payload)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_project(payload: AnalyzeRequest) -> AnalyzeResponse:
    return call_adapter(lambda: get_adapter().analyze_project(payload))


@router.post("/patch", response_model=OptimizeResponse)
def create_patch(payload: PatchRequest) -> OptimizeResponse:
    return call_adapter(lambda: get_adapter().create_patch(payload))


@router.post("/benchmark", response_model=BenchmarkResponse)
def benchmark(payload: BenchmarkRequest) -> BenchmarkResponse:
    return get_adapter().benchmark(payload)


@lru_cache
def get_adapter() -> ApiOptimizerAdapter:
    return ApiOptimizerAdapter()


def call_adapter(handler):
    try:
        return handler()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
