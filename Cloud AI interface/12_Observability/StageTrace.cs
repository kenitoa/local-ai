namespace LocalAI.CloudInterface;

public sealed class StageTrace
{
    public string Stage { get; init; } = string.Empty;
    public string Actor { get; init; } = string.Empty;
    public bool Succeeded { get; init; }
    public double DurationMs { get; init; }
    public string? InputSummary { get; init; }
    public string? OutputSummary { get; init; }
}
