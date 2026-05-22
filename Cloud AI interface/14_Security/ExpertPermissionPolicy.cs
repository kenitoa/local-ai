namespace LocalAI.CloudInterface;

public sealed class ExpertPermissionPolicy
{
    public string ExpertId { get; init; } = string.Empty;
    public ExpertPermissions Permissions { get; init; } = new();
}
