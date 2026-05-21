namespace LocalAI.CloudInterface;

public sealed class RecoveryInput
{
    public CloudAIRequest Request { get; init; } = new();
    public ExecutionPlan Plan { get; init; } = new();
    public IReadOnlyList<ExpertResult> ExpertResults { get; init; } = Array.Empty<ExpertResult>();
    public AggregatedResult? AggregatedResult { get; init; }
    public VerifiedResult? VerifiedResult { get; init; }
    public IReadOnlyList<IExpert> AvailableExperts { get; init; } = Array.Empty<IExpert>();
    public RuntimeContext Context { get; init; } = new();
}
