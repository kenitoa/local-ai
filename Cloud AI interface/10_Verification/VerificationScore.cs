namespace LocalAI.CloudInterface;

public sealed class VerificationScore
{
    public string Criterion { get; init; } = string.Empty;
    public double Score { get; init; }
    public double Weight { get; init; }
    public string Reason { get; init; } = string.Empty;
}
