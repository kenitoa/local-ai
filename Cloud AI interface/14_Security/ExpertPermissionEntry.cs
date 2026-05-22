using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class ExpertPermissionEntry
{
    [JsonPropertyName("expertId")]
    public string ExpertId { get; init; } = string.Empty;

    [JsonPropertyName("permissions")]
    public ExpertPermissions Permissions { get; init; } = new();

    public ExpertPermissionPolicy ToPolicy()
    {
        return new ExpertPermissionPolicy
        {
            ExpertId = ExpertId,
            Permissions = Permissions
        };
    }
}
