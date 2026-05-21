namespace LocalAI.CloudInterface;

public sealed class AggregationCandidate
{
    public string ExpertId { get; init; } = string.Empty;
    public string Output { get; init; } = string.Empty;
    public double Confidence { get; init; }
    public double Score { get; init; }
    public double LatencyMs { get; init; }
    public bool IsJudge { get; init; }
    public bool Succeeded { get; init; }
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();

    public Dictionary<string, object> Metadata { get; init; } = new();
}
