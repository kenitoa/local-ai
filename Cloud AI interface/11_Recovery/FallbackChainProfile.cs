namespace LocalAI.CloudInterface;

public sealed class FallbackChainProfile
{
    public string Primary { get; init; } = string.Empty;
    public IReadOnlyList<string> Fallback { get; init; } = Array.Empty<string>();
}
