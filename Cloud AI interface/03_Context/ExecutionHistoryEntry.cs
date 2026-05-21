namespace LocalAI.CloudInterface;

public sealed class ExecutionHistoryEntry
{
    public string Step { get; init; } = string.Empty;
    public string Actor { get; init; } = string.Empty;
    public string? InputSummary { get; init; }
    public string? OutputSummary { get; init; }
    public bool Succeeded { get; init; } = true;
    public TimeSpan Duration { get; init; }
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
