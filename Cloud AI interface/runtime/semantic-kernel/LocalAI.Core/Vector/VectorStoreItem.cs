namespace LocalAI.Core.Vector;

public sealed record VectorStoreItem(
    string Id,
    string DocumentId,
    string Title,
    string Chunk,
    IReadOnlyDictionary<string, double> Vector,
    DateTime CreatedAt);
