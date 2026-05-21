namespace LocalAI.CloudInterface;

public sealed class CompositionPerformanceStats
{
    public string InputType { get; init; } = string.Empty;
    public string CompositionId { get; init; } = string.Empty;
    public IReadOnlyList<string> ExpertCombination { get; init; } = Array.Empty<string>();
    public long TotalRuns { get; init; }
    public long FailedRuns { get; init; }
    public double FailureRate { get; init; }
    public double AverageJudgeScore { get; init; }
    public double AverageUserRating { get; init; }
    public double AcceptanceRate { get; init; }
    public double AverageLatencyMs { get; init; }
    public double AverageCost { get; init; }
    public double PerformanceScore { get; init; }
}
