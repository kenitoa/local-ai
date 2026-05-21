using System.Text.Json.Serialization;

namespace LocalAI.CloudInterface;

public sealed class CompositionProfileEntry
{
    [JsonPropertyName("compositionId")]
    public string CompositionId { get; init; } = string.Empty;

    [JsonPropertyName("experts")]
    public string[] Experts { get; init; } = Array.Empty<string>();

    [JsonPropertyName("strategy")]
    public string Strategy { get; init; } = CompositionStrategy.Single;

    [JsonPropertyName("fallback")]
    public string[] Fallback { get; init; } = Array.Empty<string>();

    [JsonPropertyName("requiresJudge")]
    public bool? RequiresJudge { get; init; }

    [JsonPropertyName("runInParallel")]
    public bool? RunInParallel { get; init; }

    public CompositionProfile ToProfile()
    {
        var normalizedStrategy = NormalizeStrategy(Strategy);

        return new CompositionProfile
        {
            CompositionId = CompositionId,
            Experts = Experts,
            Strategy = normalizedStrategy,
            Fallback = Fallback,
            RequiresJudge = RequiresJudge ?? normalizedStrategy == CompositionStrategy.ParallelJudge,
            RunInParallel = RunInParallel ?? normalizedStrategy is CompositionStrategy.ParallelVote or CompositionStrategy.ParallelJudge
        };
    }

    private static string NormalizeStrategy(string strategy)
    {
        var normalized = strategy.Trim().ToLowerInvariant();
        return normalized switch
        {
            CompositionStrategy.Single => CompositionStrategy.Single,
            CompositionStrategy.Pipeline => CompositionStrategy.Pipeline,
            CompositionStrategy.ParallelVote => CompositionStrategy.ParallelVote,
            CompositionStrategy.ParallelJudge => CompositionStrategy.ParallelJudge,
            CompositionStrategy.FallbackChain => CompositionStrategy.FallbackChain,
            _ => throw new ArgumentOutOfRangeException(nameof(strategy), strategy, "Unknown composition strategy.")
        };
    }
}
