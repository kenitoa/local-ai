namespace LocalAI.CloudInterface;

public sealed class ExpertTrace
{
    public string ExpertName { get; init; } = string.Empty;
    public string Stage { get; init; } = string.Empty;
    public string? InputSummary { get; init; }
    public string? OutputSummary { get; init; }
    public double Confidence { get; init; }
    public TimeSpan Duration { get; init; }
    public bool Succeeded { get; init; }
    public string? Error { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
