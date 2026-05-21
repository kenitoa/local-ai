namespace LocalAI.CloudInterface;

public sealed class TokenUsage
{
    public long InputTokens { get; init; }
    public long OutputTokens { get; init; }
    public long TotalTokens => InputTokens + OutputTokens;
}
