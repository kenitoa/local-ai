namespace LocalAI.CloudInterface;

public sealed class ExpertDefinition
{
    public ExpertProfile Profile { get; init; } = new();
    public string? ModelPath { get; init; }
    public string? Endpoint { get; init; }
    public bool Preload { get; init; }
    public bool KeepAlive { get; init; }
    public ExpertPermissions Permissions { get; init; } = new();
    public Dictionary<string, object> Settings { get; init; } = new();
}
