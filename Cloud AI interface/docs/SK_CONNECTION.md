# Semantic Kernel Connection

Semantic Kernel 연결 기준:

```text
endpoint: http://localhost:11434
modelId: llama3.1
```

커스텀 모델을 생성한 뒤에는 다음 값을 사용할 수 있습니다.

```text
modelId: local-assistant
```

예시:

```csharp
builder.AddOllamaChatCompletion(
    modelId: "llama3.1",
    endpoint: new Uri("http://localhost:11434")
);
```

Ollama 쪽 구현 목표:

1. Ollama 서버가 항상 켜져 있어야 함
2. `11434` 포트가 정상 응답해야 함
3. 지정한 `modelId`가 `ollama list`에 존재해야 함
4. `/api/chat` 또는 `/v1/chat/completions`가 정상 작동해야 함

검증:

```powershell
.\test-api.ps1 -Model llama3.1
```

Semantic Kernel 프로젝트 설정 파일:

```text
runtime/semantic-kernel/LocalAI.Api/appsettings.json
```

해당 파일의 `Ollama.Endpoint`와 `AiModel.Endpoint` 값은 `http://localhost:11434`를 기준으로 맞춥니다.

커스텀 모델을 사용할 때는 `Ollama.ModelId`와 `AiModel.ModelId` 값을 `local-assistant`로 맞춥니다.
