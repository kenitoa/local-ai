namespace AspNetAiApi;

public sealed record ChatRequest(
    string? SessionId,
    string? Model,
    string Message);

public sealed record ChatResponse(
    string SessionId,
    string Model,
    string Response,
    string Source,
    IReadOnlyList<ChatMessageDto> Messages);

public sealed record ChatMessageDto(
    string Role,
    string Content,
    DateTimeOffset CreatedAt);

public sealed record NewSessionRequest(string? Title);

public sealed record NewSessionResponse(
    string SessionId,
    string Title,
    DateTimeOffset CreatedAt);

public sealed record HealthResponse(
    string Status,
    string Api,
    string SemanticKernel,
    string Ollama);

public sealed record ModelsResponse(IReadOnlyList<string> Models);

public sealed record RagSearchRequest(string Query, int? TopK);

public sealed record RagSearchResult(
    string Id,
    string Title,
    string Snippet,
    double Score);

public sealed record RagSearchResponse(
    string Query,
    IReadOnlyList<RagSearchResult> Results);

public sealed record ToolExecuteRequest(
    string Name,
    string? Input);

public sealed record ToolExecuteResponse(
    string Name,
    string Result,
    bool Success,
    string? Error);
