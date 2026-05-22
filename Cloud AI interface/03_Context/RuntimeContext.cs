namespace LocalAI.CloudInterface;

public sealed class RuntimeContext
{
    public string SessionId { get; init; } = Guid.NewGuid().ToString("N");

    public List<Message> Conversation { get; init; } = new();
    public TaskState TaskState { get; init; } = new();
    public Dictionary<string, object> WorkingMemory { get; init; } = new();
    public Dictionary<string, object> UserMemory { get; init; } = new();

    public List<ToolResult> ToolResults { get; init; } = new();
    public List<VectorMemoryItem> VectorMemory { get; init; } = new();
    public List<ExecutionHistoryEntry> ExecutionHistory { get; init; } = new();
    public List<ExpertResult> PreviousResults { get; init; } = new();
}
