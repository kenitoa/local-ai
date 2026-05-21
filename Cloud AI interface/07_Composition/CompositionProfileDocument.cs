using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class CompositionProfileDocument
{
    [JsonPropertyName("compositions")]
    public List<CompositionProfileEntry> Compositions { get; init; } = new();
}
