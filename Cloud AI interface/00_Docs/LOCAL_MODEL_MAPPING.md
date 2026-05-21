# Local Model Mapping

`Cloud AI interface`는 이제 로컬 모델 자산을 직접 expert로 매핑한다.

## Mapped Sources

```text
local LLM model/Semantic Kernel
  -> semantic-kernel-local-ollama

runtime/ollama/server/models/manifests
  -> ollama-llama3-1-latest
  -> ollama-qwen2-5-latest
  -> ollama-local-assistant-latest
  -> ollama-nomic-embed-text-latest

local LLM model/**/*.onnx|*.zip|*.mlnet
  -> onnx-local-* or mlnet-local-*
```

## Runtime Path

```text
API / Console / local-ai runtime
  -> ICloudAI.InvokeAsync
  -> CompositionProfileRouter
  -> ParallelExecutionEngine
  -> SemanticKernelOllamaExpert or LocalModelFileExpert
  -> Aggregator
  -> RuleBasedVerifier
  -> TraceRecorder
```

## Notes

Ollama experts use the local Semantic Kernel runtime and the local Ollama endpoint.
ML.NET/ONNX file experts are mapped when model files exist under `local LLM model`; the current repository snapshot did not expose a source ML.NET model file outside build artifacts.
