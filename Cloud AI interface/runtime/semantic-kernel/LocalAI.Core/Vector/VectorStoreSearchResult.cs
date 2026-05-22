namespace LocalAI.Core.Vector;

public sealed record VectorStoreSearchResult(
    string DocumentId,
    string Title,
    string Chunk,
    double Score);
