namespace LocalAI.CloudInterface;

public sealed class OptimizationRecord
{
    public string RequestId { get; init; } = string.Empty;
    public string InputType { get; init; } = string.Empty;
    public string? SelectedComposition { get; init; }
    public IReadOnlyList<string> ExpertCombination { get; init; } = Array.Empty<string>();
    public double JudgeScore { get; init; }
    public UserFeedback? UserFeedback { get; init; }
    public double LatencyMs { get; init; }
    public double EstimatedCost { get; init; }
    public bool Failed { get; init; }
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
