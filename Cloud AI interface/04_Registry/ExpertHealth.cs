namespace LocalAI.CloudInterface;

public sealed class ExpertHealth
{
    public string ExpertId { get; init; } = string.Empty;
    public string Status { get; init; } = ExpertHealthStatus.Unknown;
    public string State { get; init; } = ExpertLifecycleState.Detached;
    public bool IsAttached { get; init; }
    public bool IsLoaded { get; init; }
    public DateTimeOffset CheckedAt { get; init; } = DateTimeOffset.UtcNow;
    public string? Message { get; init; }
    public double? LatencyMs { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
