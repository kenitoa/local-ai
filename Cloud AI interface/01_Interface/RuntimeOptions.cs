namespace LocalAI.CloudInterface;

public sealed class RuntimeOptions
{
    public string? CompositionId { get; init; }
    public IReadOnlyList<string> PreferredExperts { get; init; } = Array.Empty<string>();
    public IReadOnlyList<string> ExcludedExperts { get; init; } = Array.Empty<string>();
    public int MaxExperts { get; init; } = 3;
    public TimeSpan Timeout { get; init; } = TimeSpan.FromMinutes(2);
    public bool RequireVerification { get; init; } = true;
    public bool AllowExternalApis { get; init; }
    public double MinimumConfidence { get; init; } = 0.0;

    public Dictionary<string, object> Metadata { get; init; } = new();
}
