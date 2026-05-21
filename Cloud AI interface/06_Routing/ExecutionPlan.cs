namespace LocalAI.CloudInterface;

public sealed class ExecutionPlan
{
    public string PlanId { get; init; } = Guid.NewGuid().ToString("N");
    public List<ExecutionStep> Steps { get; init; } = new();
    public bool RequiresJudge { get; init; }
    public bool RunInParallel { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
