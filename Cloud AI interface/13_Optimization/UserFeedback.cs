namespace LocalAI.CloudInterface;

public sealed class UserFeedback
{
    public string RequestId { get; init; } = string.Empty;
    public double Rating { get; init; }
    public bool Accepted { get; init; }
    public string? Comment { get; init; }
    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;
}
