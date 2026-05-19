namespace LocalAI.Core.AI;

public sealed record ChatResponse(
    string SessionId,
    string Message,
    DateTime CreatedAt);
