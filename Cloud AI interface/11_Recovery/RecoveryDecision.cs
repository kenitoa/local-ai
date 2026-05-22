namespace LocalAI.CloudInterface;

public sealed class RecoveryDecision
{
    public bool ShouldRecover { get; init; }
    public string FailureType { get; init; } = global::LocalAI.CloudInterface.FailureType.Unknown;
    public string Action { get; init; } = global::LocalAI.CloudInterface.RecoveryAction.Stop;
    public string Reason { get; init; } = string.Empty;
    public TimeSpan Delay { get; init; }
    public IReadOnlyList<string> FallbackExpertIds { get; init; } = Array.Empty<string>();
    public string? RepairPrompt { get; init; }
    public ExecutionPlan? RetryPlan { get; init; }
    public bool RequiresModelUnload { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
