namespace LocalAI.CloudInterface;

public sealed class ExecutionStep
{
    public int Order { get; init; }
    public string ExpertId { get; init; } = string.Empty;
    public string Role { get; init; } = string.Empty;
    public string Reason { get; init; } = string.Empty;
    public bool CanRunInParallel { get; init; }
    public IReadOnlyList<string> DependsOnExpertIds { get; init; } = Array.Empty<string>();

    public Dictionary<string, object> Metadata { get; init; } = new();
}
