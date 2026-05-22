# Ollama Health Check

Semantic Kernel 앱 시작 전에는 Ollama 서버 상태와 모델 존재 여부를 확인합니다.

## 서버 상태 확인

```csharp
public static async Task<bool> CheckOllamaAsync()
{
    using var http = new HttpClient();

    try
    {
        var response = await http.GetAsync("http://localhost:11434/api/tags");
        return response.IsSuccessStatusCode;
    }
    catch
    {
        return false;
    }
}
```

사용:

```csharp
if (!await CheckOllamaAsync())
{
    Console.WriteLine("Ollama 서버가 실행 중이 아닙니다.");
    return;
}
```

## 모델 존재 여부 확인

실무에서는 문자열 검색 대신 JSON 파싱을 사용합니다. 이 저장소의 `SemanticKernelOllamaConnector.GetInstalledModelsAsync()`는 `/api/tags` 응답을 `JsonDocument`로 파싱하고 `name` 필드만 비교합니다.

엄격한 기준:

```text
1. GET /api/tags 성공 여부 확인
2. models 배열 확인
3. 각 model.name을 정확히 비교
4. modelName 또는 modelName:tag 형식 허용
5. 서버 미실행과 모델 미설치를 별도 상태로 반환
```

현재 구현:

```text
runtime/ollama/connector/IOllamaConnector.cs
runtime/ollama/connector/SemanticKernelOllamaConnector.cs
runtime/semantic-kernel/LocalAI.Console/Program.cs
runtime/semantic-kernel/LocalAI.Api/Controllers/ChatController.cs
```

콘솔 앱은 Ollama 서버가 없거나 지정 모델이 없으면 채팅 루프를 시작하지 않고 종료합니다. API는 `/api/health`에서 `ok`, `model-missing`, `ollama-unreachable` 상태를 반환합니다.
