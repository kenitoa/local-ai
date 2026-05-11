# AI Code Optimizer

Local-first code optimization workspace with a framework-independent optimizer core, optional FastAPI API, web UI, RAG storage, model runtime, workers, and Docker Compose profiles.

## Layout

- `core/optimizer_core`: Framework-independent optimization engine, retrieval, analysis, patching, evaluation, and local model runtime code.
- `adapters/cli`: CLI/TUI-first adapter that calls the core directly without HTTP.
- `adapters/api_optional`: Optional FastAPI route adapter that calls the core engine.
- `apps/api`: FastAPI service shell, API schemas, and persistence helpers.
- `apps/web`: Frontend application surface.
- `workers`: Background jobs for ingestion, evaluation, and training.
- `models`: Local model volume notes.
- `data`: RAG sources, fine-tuning datasets, and evaluation sets.
- `scripts`: Preflight, model download, dataset build, and LoRA training helpers.
- `docker`: Compose files for CPU, CUDA, train, and development modes.
- `secrets`: Local secret files mounted by Docker Compose.

## Core Boundary

FastAPI is not the owner of the optimization workflow. The primary entrypoint is:

```python
from pathlib import Path

from core.optimizer_core import CodeOptimizerEngine, OptimizeRequest

engine = CodeOptimizerEngine()
result = engine.optimize(
    OptimizeRequest(
        project_id="local-project",
        project_path=Path("/path/to/project"),
        target_files=["src/service.py"],
        user_goal="Improve performance while preserving behavior.",
        language="python",
        mode="hybrid",
    )
)
```

The API only adapts HTTP requests to this engine through `adapters/api_optional/routes.py`. This keeps `/optimize`, `/rag`, and `/jobs` replaceable by a CLI, worker, notebook, or desktop app without rewriting the optimizer.

FastAPI route functions stay intentionally thin. They delegate to `ApiOptimizerAdapter`, which calls `OptimizerWorkflow`; analysis, RAG search, patch creation, and benchmark planning live outside the router.

Core package layout:

```text
core/optimizer_core/
|-- engine.py
|-- request.py
|-- result.py
|-- config.py
`-- exceptions.py
```

`OptimizeRequest` is the API-free request object:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class OptimizeRequest:
    project_id: str
    project_path: Path
    target_files: list[str]
    user_goal: str
    language: str = "python"
    mode: str = "hybrid"  # deterministic | local_llm | hybrid
```

`OptimizeResult` is the API-free result object:

```python
from dataclasses import dataclass

@dataclass
class OptimizeResult:
    summary: str
    risk_level: str
    bottleneck: str
    patch: str
    tests_passed: bool
    benchmark_before: float | None
    benchmark_after: float | None
    confidence: float
    notes: list[str]
```

## Quick Start

CLI without API:

```bash
python -m adapters.cli.main ./project \
  --target src/main.py \
  --goal "속도 개선" \
  --mode hybrid
```

After installing the package, the same flow is available as:

```bash
ai-code-optimize ./project \
  --target src/main.py \
  --goal "속도 개선" \
  --mode hybrid
```

Useful modes:

- `deterministic`: no model call, local rules only.
- `local_llm`: local analysis plus local model patch drafting.
- `hybrid`: local rules first, model drafting only when needed.

Docker CLI runner:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
.\scripts\up.ps1
```

Linux/macOS:

```bash
cp .env.example .env
./scripts/up.sh
```

The default Docker flow starts the CLI/core `app` service. Start the `web` profile only when you want the optional browser UI at http://localhost:3000.

Default CPU-only services:

- `app`: CLI/core runner. No HTTP service is required.

Run a one-off project optimization in Docker:

```bash
docker compose -f docker/compose.yaml -f docker/compose.cpu.yaml run --rm app \
  /projects/sample \
  --target src/main.py \
  --goal "Improve speed" \
  --mode deterministic
```

Optional web/API profile:

```bash
docker compose -f docker/compose.yaml -f docker/compose.cpu.yaml --profile web up --build
```

Optional web/API services:

- `web-local`: code upload and optimization UI.
- `core-runner`: optional FastAPI adapter that calls the same local core.

Place a GGUF model at `/models/gguf/code-model-q4.gguf` inside the `model-cache` volume before relying on live LLM output. Until then, the API returns a deterministic patch draft so the MVP flow remains testable.

## Local Model Runtime

The optimizer core talks to local Python runtimes through `LocalModelRuntime`. It does not call a separate LLM HTTP server.

- `LlamaCppRuntime`: CPU profile, loads a GGUF model directly with `llama-cpp-python`.
- `VllmOfflineRuntime`: NVIDIA GPU profile, creates a `vllm.LLM` object and calls `llm.generate()` directly.
- `TransformersRuntime`: CUDA-capable fallback path for Hugging Face Transformers models.

Select the runtime with `LLM_BACKEND`:

```env
LLM_BACKEND=llama_cpp
LLAMA_CPP_MODEL_PATH=/models/gguf/code-model-q4.gguf
VLLM_MODEL_PATH=/models/base/code-model
BASE_MODEL_PATH=/models/base/code-model
```

## Code Analysis Core

The optimizer does not ask the model to guess the code structure. `core/optimizer_core/analyzer/` produces a structured `CodeAnalysis` first:

- `functions`: names, line ranges, args, calls, loop counts, return counts, and complexity.
- `classes`: class ranges and method lists.
- `imports`: module and imported symbol metadata.
- `call_graph`: function-to-call relationships for RAG reranking and patch reasoning.
- `complexity_warnings`: deterministic warnings for large, nested, or decision-heavy code.
- `optimization_opportunities`: local rule-engine findings such as `LIST_MEMBERSHIP_TO_SET`.

LLM output is only one later input. The local analyzer and rule engine decide which candidates are worth proposing before any model response is trusted.

## LLM Role

The local model is a patch drafting assistant, not the decision maker.

Local algorithms own:

- bottleneck detection
- related code selection
- optimization rule selection
- risk classification
- test and benchmark commands
- final candidate ranking

The local model may only provide:

- a unified diff patch draft
- a short explanation for that draft
- edge cases for the verifier to consider

If the model-drafted patch is not a valid unified diff or fails local syntax checks, it is discarded. The final response still uses the local analyzer's summary, risk level, bottleneck, expected effect, tests, and benchmark plan.

## Optimization Modes

Default mode is `hybrid`.

- `deterministic`: AST analysis, local rule engine, verifier, and template patches only. The local model is never called.
- `local_llm`: local analysis creates the fixed decision frame, then the local model may draft patch text.
- `hybrid`: local algorithms run first; the local model is used only when no verified local patch candidate is selected.

## GPU Profile

After the CPU MVP works, use the CUDA profile for vLLM:

```powershell
docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml run --rm app /projects/sample --target src/main.py --mode hybrid
```

The GPU profile runs the CLI/core app in a vLLM-capable image and loads the model inside the local process:

- base image: `vllm/vllm-openai:latest`
- model path: `/models/base/code-model`
- Hugging Face cache: `/models/.cache/huggingface`
- model mount: `/models`

GPU validation checklist:

1. `nvidia-smi` works on the host.
2. Docker can run `nvidia/cuda` with `--gpus all`.
3. `docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml config --services` shows `app`.
4. The app container can import `vllm` and load `/models/base/code-model`.
5. CPU profile still works when CUDA is unavailable.

Run:

```powershell
python scripts/gpu_check.py
```

## Run Scripts

Users should not choose Compose files manually. Run one script and let preflight choose the profile.

Windows:

```powershell
.\scripts\up.ps1
```

Linux/macOS:

```bash
./scripts/up.sh
```

Internally, the scripts run `scripts/preflight.py`, load `.runtime.env`, split `COMPOSE_FILES`, and execute one of:

```text
CPU-only:
docker compose -f docker/compose.yaml -f docker/compose.cpu.yaml run --rm app /projects/sample --target src/main.py --mode hybrid

NVIDIA GPU:
docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml run --rm app /projects/sample --target src/main.py --mode hybrid

Optional web UI:
docker compose -f docker/compose.yaml -f docker/compose.cpu.yaml --profile web up --build
```

PowerShell options:

```powershell
.\scripts\up.ps1 -Detach
.\scripts\up.ps1 -NoBuild
```

Bash options:

```bash
DETACH=1 ./scripts/up.sh
NO_BUILD=1 ./scripts/up.sh
```

## Security And Secrets

Do not put Hugging Face tokens, private model tokens, database passwords, or package registry tokens into Docker images or committed `.env` files.

Create secret files locally:

```powershell
Copy-Item secrets/hf_token.txt.example secrets/hf_token.txt
```

Compose mounts them into containers as:

```text
/run/secrets/hf_token
```

API code can read secrets with:

```python
from app.services.secrets import read_secret

hf_token = read_secret("hf_token")
```

## API Endpoints

Initial API surface:

```text
GET  /health
GET  /ready
POST /projects
POST /projects/{project_id}/files
POST /rag/ingest
POST /rag/search
POST /optimize/analyze
POST /optimize/patch
POST /optimize/benchmark
GET  /jobs/{job_id}
```

Flow:

```text
사용자 코드 업로드
-> 프로젝트 생성
-> 코드 파일 저장
-> RAG 인덱싱
-> 사용자가 "이 코드 최적화해줘" 요청
-> 정적 분석 실행
-> RAG 검색
-> LLM 프롬프트 생성
-> 개선안/패치 반환
```

`/health` only checks that the API process is alive. `/ready` checks runtime configuration, storage readiness, RAG index path readiness, and selected LLM settings.

## RAG Indexing

The optimizer RAG index is split by collection:

```text
project_code_chunks
optimization_knowledge
past_patches
error_logs
benchmark_results
```

Every chunk stores payload metadata:

```json
{
  "project_id": "abc123",
  "language": "python",
  "file_path": "src/service.py",
  "symbol": "calculate_score",
  "chunk_type": "function",
  "hash": "sha256:...",
  "line_start": 10,
  "line_end": 87,
  "calls": ["math.sqrt", "sum"],
  "imports": ["math"]
}
```

Code indexing prefers structure over blind character splitting:

1. Parse file-level metadata.
2. Split Python functions/classes with `ast`.
3. Store imports/dependency information separately.
4. Split large or unsupported files into overlapping line blocks.
5. Preserve file path, language, symbol, and line range in metadata.

RAG does not require a vector database service. The core stores local indexes under `data/indexes/<project_id>/`, embeds text locally with `sentence-transformers`, and uses FAISS when installed. Each project index keeps `faiss.index`, `metadata.jsonl`, `keyword_index.pkl`, and `symbol_graph.json` together. If the embedding model or native vector library is unavailable, deterministic hash embeddings and Python cosine search keep the flow testable.

Search is not pure vector top-k. The local reranker combines semantic similarity, keyword overlap, symbol matches, call/import relationships, and file path relevance:

```text
final_score =
  0.35 * dense_similarity
+ 0.25 * keyword_score
+ 0.20 * symbol_match_score
+ 0.10 * call_graph_distance_score
+ 0.10 * file_path_relevance_score
```

Each search result includes `metadata.ranker` with those component scores, so the engine can explain why a chunk was selected.

Embedding model settings:

```env
EMBEDDING_BACKEND=sentence_transformers
EMBEDDING_MODEL_PATH=/models/embeddings/code-search
EMBEDDING_DIMENSION=384
```

For code optimization, keep a code-oriented embedding model in the local model volume rather than relying on a generic external embedding API.

## Optimization Pipeline

The optimizer does not pass a vague "improve this code" request directly to the LLM. The core algorithm analyzes, searches, generates rule-based candidates, verifies them, and only uses the LLM when the local algorithm cannot produce a safe patch.

```text
1. Parse code with tree-sitter when available, otherwise language-native parsers.
2. Run static analysis.
3. Estimate complexity and risky syntax.
4. Detect bottleneck patterns.
5. Search local RAG context.
6. Match optimization rules.
7. Generate local patch candidates.
8. Verify syntax, unified diff shape, and public symbols.
9. Rank candidates by risk and score.
10. Select the best verified patch.
11. Use the LLM only as a fallback or explanation assistant.
```

Initial Python rules:

```text
PY001: Replace x = x + y with x += y when the target is identical.
PY002: Replace constant list membership with set membership.
PY003: Replace simple len(x) > 0 checks with truthiness.
PY004: Flag nested loops for benchmark-driven redesign.
PY005: Flag eval/exec as unsafe for automatic optimization.
PY006: Flag bare except blocks.
PY007: Preserve import structure during rewrites.
PY008: Suggest local bindings for repeated global lookups.
PY009: Suggest removing unnecessary deepcopy.
PY010: Suggest memoization for repeatable pure calls.
```

Optimization responses are forced into this JSON shape:

```json
{
  "summary": "무엇을 최적화했는지",
  "risk_level": "low | medium | high",
  "bottleneck": "병목 원인",
  "patch": "unified diff",
  "expected_effect": "예상 성능/가독성/메모리 개선",
  "test_command": "pytest",
  "benchmark_command": "python -m pytest --benchmark-only",
  "notes": ["주의사항"]
}
```

Patch application is intentionally not automatic. The first phase only proposes a unified diff; applying it and committing after tests should be a separate workflow.

## Training Data Collection

Fine-tuning is not started directly. The system first collects code optimization records under `data/fine_tune`.

Collected fields:

```text
1. 사용자 요청
2. 대상 코드
3. RAG 검색 결과
4. 정적 분석 결과
5. AI가 제안한 패치
6. 사용자가 승인했는지
7. 테스트 통과 여부
8. 벤치마크 결과
9. 최종 적용 여부
10. 사람이 수정한 최종 패치
```

Dataset quality:

```text
gold   = 테스트 통과 + 성능 개선 + 사람 승인
silver = 테스트 통과 + 사람 승인
bronze = AI 제안만 있고 검증 부족
```

Build data:

```powershell
python scripts/build_dataset.py --write-template
python scripts/build_dataset.py
```

Use `--include-bronze` only for exploratory analysis. Fine-tuning should start with `gold` and selected `silver`.

## LoRA / QLoRA Fine-Tuning

Run fine-tuning only after the CUDA profile is stable. CPU-only machines should keep collecting data and should not run training.

Order:

```text
1. Select base coder model.
2. Build training JSONL.
3. Split train/valid/test.
4. Set PEFT LoRA parameters.
5. Run a short smoke training pass.
6. Validate on a small eval set.
7. Run full training.
8. Save LoRA adapter.
9. Connect adapter to inference.
10. Compare against the RAG-only baseline.
```

Build data:

```powershell
python scripts/build_dataset.py --write-template
python scripts/build_dataset.py
```

Validate the dataset without loading model libraries:

```powershell
python scripts/train_lora.py --dry-run
```

GPU training through Compose:

```powershell
docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml -f docker/compose.train.yaml run --rm trainer
```

Smoke training:

```powershell
docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml -f docker/compose.train.yaml run --rm trainer python scripts/train_lora.py --dataset /workspace/data/fine_tune/splits/train.jsonl --output /checkpoints/code-optimizer-lora-smoke --qlora --smoke --max-steps 5
```

## Connect LoRA Adapter

Store fine-tuning output as an adapter, not as a full base model copy:

```text
/models/
├─ base/
│  └─ code-model/
├─ adapters/
│  └─ code-optimizer-lora/
└─ gguf/
   └─ code-model-q4.gguf
```

Base-only GPU profile:

```powershell
docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml up --build
```

RAG + LoRA profile:

```powershell
docker compose -f docker/compose.yaml -f docker/compose.cuda.yaml -f docker/compose.lora.yaml up --build
```

Compare base-only and LoRA responses against the same prompt:

```powershell
python scripts/compare_lora.py --model-path /models/base/code-model
```

RAG remains required. RAG provides current project code, libraries, configs, tests, and long-context evidence. LoRA teaches response style, patch structure, bottleneck reasoning, and user preferences.

## Evaluation And Benchmarking

Code optimization needs an evaluation loop, not only a plausible answer.

Evaluation checks:

```text
1. Can the patch be applied?
2. Do tests pass?
3. Did runtime improve or avoid regression?
4. Did memory usage avoid regression if measured?
5. Did readability avoid getting worse?
6. Did public API behavior remain stable?
7. Is the explanation accurate?
```

Evaluation datasets live under:

```text
data/eval_sets/
|-- python_small/
|-- python_medium/
|-- js_small/
`-- real_world_cases/
```

Each case contains:

```text
case_001/
|-- input.py
|-- tests/
|-- benchmark.py
|-- expected_notes.md
`-- metadata.json
```

Run:

```powershell
python scripts/run_eval.py
```

To evaluate model outputs, pass a candidate JSON keyed by `case_id` with the same response fields used by `/optimize/patch`, especially `patch`, `summary`, `risk_level`, `bottleneck`, `expected_effect`, `test_command`, and `benchmark_command`.

## Preflight

Run `scripts/preflight.py` before starting Docker. It checks the host OS, CPU cores, RAM, Docker daemon, NVIDIA GPU visibility, `nvidia-smi`, Docker GPU runtime access, common service ports, and then writes:

- `.runtime.env`
- `.runtime.json`

CPU output selects:

```env
AI_DEVICE=cpu
LLM_BACKEND=llama_cpp
COMPOSE_FILES=docker/compose.yaml:docker/compose.cpu.yaml
MODEL_RUNTIME=llama-cpp-python
LLAMA_CPP_MODEL_PATH=/models/gguf/code-model-q4.gguf
MODEL_DIR=/models
HF_HOME=/models/.cache/huggingface
```

CUDA output selects:

```env
AI_DEVICE=cuda
LLM_BACKEND=vllm
COMPOSE_FILES=docker/compose.yaml:docker/compose.cuda.yaml
MODEL_RUNTIME=vllm-offline
VLLM_MODEL_PATH=/models/base/code-model
MODEL_DIR=/models
HF_HOME=/models/.cache/huggingface
```
