namespace LocalAI.CloudInterface;

public sealed class VectorMemoryItem
{
    public string Id { get; init; } = Guid.NewGuid().ToString("N");
    public string Text { get; init; } = string.Empty;
    public double[] Embedding { get; init; } = Array.Empty<double>();
    public double Score { get; init; }
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
