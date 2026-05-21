using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class FallbackChainEntry
{
    [JsonPropertyName("primary")]
    public string Primary { get; init; } = string.Empty;

    [JsonPropertyName("fallback")]
    public string[] Fallback { get; init; } = Array.Empty<string>();

    public FallbackChainProfile ToProfile()
    {
        return new FallbackChainProfile
        {
            Primary = Primary,
            Fallback = Fallback
        };
    }
}
