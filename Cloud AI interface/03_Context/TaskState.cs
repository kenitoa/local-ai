namespace LocalAI.CloudInterface;

public sealed class TaskState
{
    public string? Goal { get; init; }
    public string Status { get; set; } = "pending";
    public List<string> CompletedSteps { get; init; } = new();
    public List<string> PendingSteps { get; init; } = new();

    public Dictionary<string, object> Metadata { get; init; } = new();
}
