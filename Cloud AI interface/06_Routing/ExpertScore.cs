namespace LocalAI.CloudInterface;

public sealed class ExpertScore
{
    public string ExpertId { get; init; } = string.Empty;
    public double CapabilityMatch { get; init; }
    public double QualityScore { get; init; }
    public double SuccessRate { get; init; }
    public double LatencyPenalty { get; init; }
    public double CostPenalty { get; init; }
    public double MemoryPenalty { get; init; }
    public double TotalScore { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
