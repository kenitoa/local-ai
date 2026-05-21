namespace LocalAI.CloudInterface;

public sealed class MvpFeatureStatus
{
    public int MvpLevel { get; init; }
    public string Feature { get; init; } = string.Empty;
    public bool Implemented { get; init; }
    public string Evidence { get; init; } = string.Empty;
}
