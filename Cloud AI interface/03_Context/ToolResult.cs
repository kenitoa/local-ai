namespace LocalAI.CloudInterface;

public sealed class ToolResult
{
    public string ToolName { get; init; } = string.Empty;
    public string Output { get; init; } = string.Empty;
    public bool Succeeded { get; init; } = true;
    public string? Error { get; init; }
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
