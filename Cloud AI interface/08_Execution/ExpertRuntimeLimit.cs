namespace LocalAI.CloudInterface;

public sealed class ExpertRuntimeLimit
{
    public int MaxConcurrentRequests { get; init; } = 1;
    public TimeSpan Timeout { get; init; } = TimeSpan.FromMinutes(2);
    public int MaxRetries { get; init; }
    public TimeSpan MinDelayBetweenRequests { get; init; } = TimeSpan.Zero;
    public int CircuitBreakerFailureThreshold { get; init; } = 3;
    public TimeSpan CircuitBreakerBreakDuration { get; init; } = TimeSpan.FromSeconds(30);
    public long MaxMemoryMb { get; init; }
}
