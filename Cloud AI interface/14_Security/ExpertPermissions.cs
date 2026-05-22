namespace LocalAI.CloudInterface;

public sealed class ExpertPermissions
{
    public bool CanAccessInternet { get; init; }
    public bool CanReadFiles { get; init; }
    public bool CanWriteFiles { get; init; }
    public bool CanCallExternalApi { get; init; }
    public bool CanUseTools { get; init; }
    public bool CanReceiveUserData { get; init; } = true;
    public bool CanReceiveSensitiveData { get; init; }
    public bool RunInSandbox { get; init; } = true;
    public IReadOnlyList<string> AllowedTools { get; init; } = Array.Empty<string>();
}
