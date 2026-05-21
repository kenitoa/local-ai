using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class ExpertRegistryEntry
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;

    [JsonPropertyName("provider")]
    public string Provider { get; init; } = string.Empty;

    [JsonPropertyName("type")]
    public string ModelType { get; init; } = string.Empty;

    [JsonPropertyName("capabilities")]
    public string[] Capabilities { get; init; } = Array.Empty<string>();

    [JsonPropertyName("priority")]
    public int Priority { get; init; } = 100;

    [JsonPropertyName("costScore")]
    public double CostScore { get; init; }

    [JsonPropertyName("latencyScore")]
    public double LatencyScore { get; init; }

    [JsonPropertyName("qualityScore")]
    public double QualityScore { get; init; }

    [JsonPropertyName("requiredMemoryMb")]
    public long RequiredMemoryMb { get; init; }

    [JsonPropertyName("supportsStreaming")]
    public bool SupportsStreaming { get; init; }

    [JsonPropertyName("supportsJsonOutput")]
    public bool SupportsJsonOutput { get; init; } = true;

    [JsonPropertyName("modelPath")]
    public string? ModelPath { get; init; }

    [JsonPropertyName("endpoint")]
    public string? Endpoint { get; init; }

    [JsonPropertyName("preload")]
    public bool Preload { get; init; }

    [JsonPropertyName("keepAlive")]
    public bool KeepAlive { get; init; }

    [JsonPropertyName("settings")]
    public Dictionary<string, object> Settings { get; init; } = new();

    public ExpertProfile ToProfile()
    {
        return new ExpertProfile
        {
            Id = Id,
            Provider = Provider,
            ModelType = ModelType,
            Capabilities = Capabilities,
            Priority = Priority,
            CostScore = CostScore,
            LatencyScore = LatencyScore,
            QualityScore = QualityScore,
            RequiredMemoryMb = RequiredMemoryMb,
            SupportsStreaming = SupportsStreaming,
            SupportsJsonOutput = SupportsJsonOutput
        };
    }
}
