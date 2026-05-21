namespace LocalAI.CloudInterface;

public sealed class AggregatedResult
{
    public string Output { get; init; } = string.Empty;
    public double Confidence { get; init; }
    public string Strategy { get; init; } = AggregationStrategy.WeightedScore;
    public string? SelectedExpertId { get; init; }
    public IReadOnlyList<string> UsedExperts { get; init; } = Array.Empty<string>();
    public IReadOnlyList<AggregationCandidate> Candidates { get; init; } = Array.Empty<AggregationCandidate>();
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();
    public bool Succeeded { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
