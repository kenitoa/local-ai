# LocalAI Semantic Kernel Deployment

## Project Layout

- `LocalAI.Core`: Semantic Kernel setup, chat session, plugins, RAG, vector store, security filters, model options.
- `../runtime/ollama/connector`: Ollama model/endpoint options, `HttpClient` timeout, Semantic Kernel Ollama registration, OpenAI-compatible fallback, streaming chat service access, and `/api/tags` health/model checks.
- `LocalAI.Console`: first-pass local validation console.
- `LocalAI.Api`: ASP.NET API wrapper for WPF, Avalonia, Unity, and web clients.
- `../ui/wpf`: WPF client using HTTP API.
- `../ui/avalonia`: Avalonia client using HTTP API.

## Runtime Requirements

- .NET 10 SDK
- Ollama running at `http://localhost:11434`
- Model configured in `LocalAI.Api/appsettings.json`

Default model:

```json
{
  "AiModel": {
    "Provider": "Ollama",
    "ModelId": "llama3.1",
    "Endpoint": "http://localhost:11434",
    "ServiceId": "local-ollama",
    "TimeoutSeconds": 180,
    "EnableFunctionCalling": true
  },
  "Ollama": {
    "ModelId": "llama3.1",
    "Endpoint": "http://localhost:11434",
    "ServiceId": "local-ollama",
    "TimeoutSeconds": 180,
    "EnableFunctionCalling": true
  }
}
```

## Ollama Connector Flow

```text
App UI
  -> ChatService / AIService
  -> Ollama Connector
  -> Semantic Kernel
  -> Ollama Local API
  -> Local LLM
```

The API and UI layers do not call `AddOllamaChatCompletion` directly. `SemanticKernelOllamaConnector` owns:

- model id, endpoint, service id, timeout, and function-calling toggle
- explicit `HttpClient` creation
- native `AddOllamaChatCompletion` registration
- OpenAI-compatible fallback against `http://localhost:11434/v1`
- `IChatCompletionService` lookup
- `/api/tags` connection and installed-model checks

To switch models, edit `LocalAI.Api/appsettings.json`:

```json
{
  "Ollama": {
    "ModelId": "qwen2.5-coder",
    "Endpoint": "http://localhost:11434",
    "ServiceId": "local-ollama",
    "TimeoutSeconds": 180,
    "EnableFunctionCalling": false
  }
}
```

Use `Provider: "OpenAICompatible"` when the native experimental Ollama connector is unstable. The connector appends `/v1` to the configured endpoint if needed.

## Connector Stabilization Checklist

- [x] Ollama 실행 여부 확인: `IOllamaConnector.CheckConnectionAsync()` calls `GET /api/tags`; `/api/health` exposes `ok` or `ollama-unreachable`.
- [x] 모델 설치 여부 확인: `IOllamaConnector.CheckModelInstalledAsync()` compares the configured `ModelId` with installed model names from `/api/tags`; `/api/health` exposes `ModelInstalled`.
- [x] endpoint 분리: `OllamaConnectorOptions.Endpoint` and `AiModelOptions.Endpoint` keep the Ollama URL out of UI code.
- [x] modelId 분리: `OllamaConnectorOptions.ModelId` and `appsettings.json` control the active local model.
- [x] timeout 설정: `OllamaConnectorOptions.TimeoutSeconds` controls the chat `HttpClient`; health checks use a separate 5-second timeout.
- [x] cancellationToken 지원: chat, streaming, health, and model-list calls pass cancellation tokens; explicit caller cancellation is not swallowed as a false health result.
- [x] streaming 지원: `ChatSession.StreamAsync()` uses Semantic Kernel streaming and the API writes SSE-safe `data:` frames.
- [x] ChatHistory 관리: `IChatSessionStore` keeps session histories, and `SemanticKernelChatService` serializes access per session to avoid concurrent mutation.
- [x] system prompt 관리: `SystemPrompts` loads prompt files from `Prompts/*.txt`, and new sessions start with `default-assistant.txt`.
- [x] function calling 가능 여부 확인: `EnableFunctionCalling` controls `PromptExecutionSettings`; plugin registration remains independent from the toggle.
- [x] fallback connector 준비: `OllamaConnectorMode.OpenAICompatible` routes through Semantic Kernel OpenAI-compatible registration against `/v1`.
- [x] UI 계층과 완전 분리: UI/API callers use chat services and `IOllamaConnector`; UI code does not call Semantic Kernel Ollama registration directly.

## Final Recommended Implementation Order

1. Ollama 설치 및 모델 pull: `ollama serve`, `ollama pull llama3.1`, `ollama list`.
2. Semantic Kernel 패키지 설치: `Microsoft.SemanticKernel`, `Microsoft.SemanticKernel.Connectors.Ollama`, `Microsoft.SemanticKernel.Connectors.OpenAI`.
3. `OllamaConnectorOptions` 작성: model, endpoint, service id, timeout, function-calling toggle, connector mode.
4. `IOllamaConnector` 인터페이스 작성: kernel creation, chat service lookup, health check, installed-model check.
5. `SemanticKernelOllamaConnector` 작성: native Ollama connector plus OpenAI-compatible fallback.
6. Kernel 생성 로직 분리: `LocalAI.Core` uses `IOllamaConnector` instead of calling `AddOllamaChatCompletion` directly.
7. `IChatCompletionService` 생성 로직 분리: connector owns service registration and lookup.
8. Local chat service 작성: `SemanticKernelChatService` is the app-facing chat service.
9. `ChatHistory` 누적 처리: `IChatSessionStore` stores successful session histories; failed calls do not mutate the saved history.
10. Streaming 응답 추가: `ChatSession.StreamAsync()` and `/api/chat/stream` support token streaming with SSE-safe frames.
11. Health Check 추가: `/api/health` reports API, provider, endpoint, service id, function-calling state, and model installation state.
12. `appsettings.json`으로 모델/endpoint 분리: `AiModel` and `Ollama` sections keep runtime config out of UI code.
13. Plugin 등록 구조 추가: `KernelFactory` registers system/file/NAS/search/memory/command plugins through the connector builder hook.
14. Function calling 테스트: `EnableFunctionCalling` controls auto function calling without removing plugin registration.
15. OpenAI 호환 fallback connector 추가: `Provider: "OpenAICompatible"` uses `http://localhost:11434/v1`.
16. Console -> WPF/WinUI/Avalonia/API로 확장: clients call the ASP.NET API at `http://localhost:5089` and use the shared API response contract.

## Final Verification Cases

- Build: `dotnet build .\LocalAI.sln --no-restore -v:minimal` passes with 0 warnings and 0 errors.
- WPF client build: `dotnet build ..\ui\wpf\WpfDesktopMvp.csproj --no-restore -v:minimal` passes with 0 warnings and 0 errors.
- cli missing: console starts and reports `Ollama: not reachable` instead of crashing.
- Ollama endpoint down: `/api/health` returns `status=ollama-unreachable` and `modelInstalled=false`.
- Model list when endpoint down: `/api/models` returns an empty installed model list plus `configuredModel`, so installed and configured models are not confused.
- Chat when endpoint down: `/api/chat` returns HTTP 503 with `error=ollama-unavailable` instead of an unhandled Kestrel exception.
- Session creation without Ollama: `/api/session` still returns a session id because session state does not require a running model.
- Streaming failure path: `/api/chat/stream` emits an SSE `error` event for Ollama transport failures.
- Chat history failure path: chat history is cloned before model calls and saved only on success, preventing user-only messages from being persisted after failed calls.
- UI expansion path: WPF, WinUI, and Avalonia client contracts match the Semantic Kernel API `HealthResponse`, `ModelsResponse`, and `ChatResponse` shapes.

## Build

Run from this directory:

```powershell
dotnet build .\LocalAI.sln --no-restore -v:minimal
```

If packages were not restored yet:

```powershell
dotnet build .\LocalAI.sln -v:minimal
```

## Console Validation

```powershell
dotnet run --project .\LocalAI.Console\LocalAI.Console.csproj
```

Check:

- Ollama connection
- model response speed
- Korean response quality
- chat history continuity
- plugin calling behavior
- exception handling
- streaming output

## API Runtime

```powershell
dotnet run --project .\LocalAI.Api\LocalAI.Api.csproj
```

Default API URL:

```text
http://localhost:5089
```

## API Endpoints

- `GET /api/health`
- `GET /api/models`
- `POST /api/session`
- `DELETE /api/session/{id}`
- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/rag/documents`
- `POST /api/rag/search`
- `POST /api/tools/execute`

## Security Defaults

Dangerous operations are disabled by default:

```json
{
  "Plugins": {
    "WorkspaceRoot": ".",
    "NasRootPath": "",
    "AllowFileDelete": false,
    "AllowCommandExecution": false,
    "AllowNasControl": false
  }
}
```

Keep these disabled unless the caller is an explicit trusted UI action with user confirmation.

## Client Connection

WPF and Avalonia clients should point to:

```text
http://localhost:5089
```

The API hides Semantic Kernel and Ollama from UI clients:

```text
WPF / Avalonia / Unity / Web
  -> ASP.NET API
  -> Ollama Connector
  -> Semantic Kernel
  -> Ollama
```

## Deployment Notes

- Do not deploy `bin/`, `obj/`, or local package caches as source.
- Do not commit real API keys or NAS credentials.
- Keep `appsettings.json` safe for local defaults only.
- For NAS deployment, set `Plugins:NasRootPath` to the mounted NAS path and keep destructive permissions disabled by default.
