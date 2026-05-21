namespace LocalAI.CloudInterface;

public sealed class ExpertProfile
{
    public string Id { get; init; } = string.Empty;
    public string Provider { get; init; } = string.Empty;
    public string ModelType { get; init; } = string.Empty;

    public string[] Capabilities { get; init; } = Array.Empty<string>();

    public int Priority { get; init; }
    public double CostScore { get; init; }
    public double LatencyScore { get; init; }
    public double QualityScore { get; init; }

    public long RequiredMemoryMb { get; init; }
    public bool SupportsStreaming { get; init; }
    public bool SupportsJsonOutput { get; init; }
}
