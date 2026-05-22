namespace LocalAI.CloudInterface;

public sealed class CompositionProfile
{
    public string CompositionId { get; init; } = string.Empty;
    public IReadOnlyList<string> Experts { get; init; } = Array.Empty<string>();
    public string Strategy { get; init; } = CompositionStrategy.Single;
    public IReadOnlyList<string> Fallback { get; init; } = Array.Empty<string>();
    public bool RequiresJudge { get; init; }
    public bool RunInParallel { get; init; }

    public Dictionary<string, object> Metadata { get; init; } = new();
}
