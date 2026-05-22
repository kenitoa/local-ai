namespace LocalAI.Core.Rag;

public sealed record RagDocument(
    string Id,
    string Title,
    string Content,
    DateTime CreatedAt);
