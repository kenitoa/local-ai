namespace LocalAI.CloudInterface;

public sealed class Message
{
    public string Role { get; init; } = string.Empty;
    public string Content { get; init; } = string.Empty;
    public string? Name { get; init; }
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
