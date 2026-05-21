namespace LocalAI.CloudInterface;

public sealed class ExpertHistoricalStats
{
    public string ExpertId { get; init; } = string.Empty;
    public long TotalRuns { get; init; }
    public long SuccessfulRuns { get; init; }
    public double SuccessRate { get; init; } = 0.5;
    public double AverageLatencyMs { get; init; }
    public double AverageJudgeScore { get; init; }
}
