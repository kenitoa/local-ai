namespace LocalAI.CloudInterface;

public sealed class SecurityViolation
{
    public string Code { get; init; } = string.Empty;
    public string Message { get; init; } = string.Empty;
    public string Severity { get; init; } = "warning";
}
