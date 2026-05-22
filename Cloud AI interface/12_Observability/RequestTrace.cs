namespace LocalAI.CloudInterface;

public sealed class RequestTrace
{
    public string RequestId { get; init; } = string.Empty;
    public string SessionId { get; init; } = string.Empty;
    public string? Composition { get; init; }
    public IReadOnlyList<string> SelectedExperts { get; init; } = Array.Empty<string>();
    public string RouterDecision { get; init; } = string.Empty;
    public double LatencyMs { get; init; }
    public TokenUsage TokenUsage { get; init; } = new();
    public MemoryUsage MemoryUsage { get; init; } = new();
    public IReadOnlyList<ExpertOutputTrace> ExpertOutputs { get; init; } = Array.Empty<ExpertOutputTrace>();
    public double JudgeScore { get; init; }
    public string FinalAnswer { get; init; } = string.Empty;
    public bool FallbackUsed { get; init; }
    public bool Error { get; init; }
    public IReadOnlyList<string> Errors { get; init; } = Array.Empty<string>();
    public IReadOnlyList<StageTrace> Stages { get; init; } = Array.Empty<StageTrace>();
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
