namespace LocalAI.CloudInterface;

public sealed class ExpertResult
{
    public string ExpertId { get; init; } = string.Empty;
    public string Output { get; init; } = string.Empty;
    public double Confidence { get; init; }
    public bool Succeeded { get; init; } = true;
    public bool Success => Succeeded;
    public bool IsJsonOutput { get; init; }
    public TimeSpan Duration { get; init; }
    public double LatencyMs { get; init; }
    public string? Error { get; init; }
    public string[] Warnings { get; init; } = Array.Empty<string>();

    public Dictionary<string, object> Metadata { get; init; } = new();
}
