from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    project_name: str = Field(default="local-upload")
    project_id: str | None = None
    language: str = Field(default="python")
    goal: str = Field(default="Improve performance while preserving behavior.")
    mode: str = Field(default="hybrid", pattern="^(deterministic|local_llm|hybrid)$")
    code: str


class AnalyzeRequest(BaseModel):
    project_id: str
    goal: str = Field(default="Find optimization opportunities.")


class AnalyzeResponse(BaseModel):
    project_id: str
    findings: list[dict[str, object]]
    rag_context: list[str] = Field(default_factory=list)


class PatchRequest(BaseModel):
    project_id: str
    goal: str = Field(default="Improve performance while preserving behavior.")
    language: str = Field(default="python")
    mode: str = Field(default="hybrid", pattern="^(deterministic|local_llm|hybrid)$")
    path: str | None = None
    code: str | None = None


class BenchmarkRequest(BaseModel):
    project_id: str
    command: str = Field(default="pytest")
    language: str = Field(default="python")


class BenchmarkResponse(BaseModel):
    job_id: str
    status: str
    checks: list[str]


class OptimizeResponse(BaseModel):
    summary: str = ""
    risk_level: str = "medium"
    bottleneck: str = ""
    explanation: str
    patch: str
    expected_effect: str = ""
    test_command: str = ""
    benchmark_command: str = ""
    checks: list[str]
    notes: list[str] = Field(default_factory=list)
    rag_context: list[str] = Field(default_factory=list)
    llm_backend: str = "fallback"
