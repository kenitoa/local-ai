namespace LocalAI.CloudInterface;

public sealed class ExpertOutputTrace
{
    public string ExpertId { get; init; } = string.Empty;
    public string Output { get; init; } = string.Empty;
    public double Confidence { get; init; }
    public bool Succeeded { get; init; }
    public double LatencyMs { get; init; }
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();
    public string? Error { get; init; }
}
