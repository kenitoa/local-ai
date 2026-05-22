namespace LocalAI.Core.AI;

public sealed record ChatRequest(
    string SessionId,
    string Message,
    string? Model = null);
