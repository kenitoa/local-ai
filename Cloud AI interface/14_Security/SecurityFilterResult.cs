namespace LocalAI.CloudInterface;

public sealed class SecurityFilterResult
{
    public bool Allowed { get; init; } = true;
    public ExpertRequest Request { get; init; } = new();
    public IReadOnlyList<SecurityViolation> Violations { get; init; } = Array.Empty<SecurityViolation>();
}
