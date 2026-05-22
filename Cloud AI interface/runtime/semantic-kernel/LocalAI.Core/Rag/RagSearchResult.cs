namespace LocalAI.Core.Rag;

public sealed record RagSearchResult(
    string DocumentId,
    string Title,
    string Chunk,
    double Score);
