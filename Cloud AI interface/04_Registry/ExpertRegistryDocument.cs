using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class ExpertRegistryDocument
{
    [JsonPropertyName("experts")]
    public List<ExpertRegistryEntry> Experts { get; init; } = new();
}
