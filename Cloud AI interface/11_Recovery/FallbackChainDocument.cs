using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class FallbackChainDocument
{
    [JsonPropertyName("chains")]
    public List<FallbackChainEntry> Chains { get; init; } = new();
}
