namespace LocalAI.CloudInterface;

public sealed class TraceRecordInput
{
    public CloudAIRequest Request { get; init; } = new();
    public ExecutionPlan? Plan { get; init; }
    public IReadOnlyList<ExpertResult> ExpertResults { get; init; } = Array.Empty<ExpertResult>();
    public AggregatedResult? AggregatedResult { get; init; }
    public VerifiedResult? VerifiedResult { get; init; }
    public RecoveryDecision? RecoveryDecision { get; init; }
    public RuntimeContext Context { get; init; } = new();
    public DateTimeOffset StartedAt { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset CompletedAt { get; init; } = DateTimeOffset.UtcNow;
}
