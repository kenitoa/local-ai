namespace LocalAI.CloudInterface;

public sealed class CloudAIResponse
{
    public string Output { get; init; } = string.Empty;
    public double Confidence { get; init; }

    public IReadOnlyList<string> UsedExperts { get; init; } = Array.Empty<string>();
    public IReadOnlyList<ExpertTrace> Trace { get; init; } = Array.Empty<ExpertTrace>();

    public Dictionary<string, object> Metadata { get; init; } = new();
}
