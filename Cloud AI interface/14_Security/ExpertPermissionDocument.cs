using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class ExpertPermissionDocument
{
    [JsonPropertyName("policies")]
    public List<ExpertPermissionEntry> Policies { get; init; } = new();
}
