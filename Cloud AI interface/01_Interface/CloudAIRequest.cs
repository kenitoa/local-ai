namespace LocalAI.CloudInterface;

public sealed class CloudAIRequest
{
    public string RequestId { get; init; } = Guid.NewGuid().ToString("N");
    public string UserId { get; init; } = "anonymous";
    public string Input { get; init; } = string.Empty;

    public string? TaskType { get; init; }

    public Dictionary<string, object> Context { get; init; } = new();
    public RuntimeContext SharedContext { get; init; } = new();
    public RuntimeOptions Options { get; init; } = new();
}
