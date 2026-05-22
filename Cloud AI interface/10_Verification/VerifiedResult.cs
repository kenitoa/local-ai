namespace LocalAI.CloudInterface;

public sealed class VerifiedResult
{
    public string WinnerExpertId { get; init; } = string.Empty;
    public double Score { get; init; }
    public string Reason { get; init; } = string.Empty;
    public string FinalAnswer { get; init; } = string.Empty;
    public bool NeedsRetry { get; init; }
    public IReadOnlyList<VerificationScore> Scores { get; init; } = Array.Empty<VerificationScore>();
    public IReadOnlyList<string> Conflicts { get; init; } = Array.Empty<string>();
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();

    public Dictionary<string, object> Metadata { get; init; } = new();
}
