namespace LocalAI.CloudInterface;

public sealed class OptimizationRecommendation
{
    public string InputType { get; init; } = string.Empty;
    public string? CompositionId { get; init; }
    public IReadOnlyList<string> ExpertCombination { get; init; } = Array.Empty<string>();
    public double Score { get; init; }
    public string Reason { get; init; } = string.Empty;
    public CompositionPerformanceStats? Stats { get; init; }
}
