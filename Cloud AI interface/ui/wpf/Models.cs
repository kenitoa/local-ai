namespace WpfDesktopMvp;

public sealed record ChatMessageView(string Role, string Content);

public sealed record HealthResponse(
    string Status,
    string Api,
    string Provider,
    string ModelId,
    string Endpoint,
    string ServiceId,
    int TimeoutSeconds,
    bool EnableFunctionCalling,
    bool ModelInstalled);

public sealed record ModelsResponse(
    IReadOnlyList<string> Models,
    string ConfiguredModel,
    bool OllamaReachable);

public sealed record NewSessionRequest(string Title);

public sealed record NewSessionResponse(
    string SessionId,
    DateTime CreatedAt);

public sealed record ChatRequest(
    string? SessionId,
    string Model,
    string Message);

public sealed record ChatResponse(
    string SessionId,
    string Message,
    DateTime CreatedAt);

public sealed record ApiChatMessage(
    string Role,
    string Content,
    DateTimeOffset CreatedAt);

public sealed record ToolExecuteRequest(string Name, string Input);

public sealed record ToolExecuteResponse(
    string Name,
    string Result,
    bool Success,
    string? Error);
