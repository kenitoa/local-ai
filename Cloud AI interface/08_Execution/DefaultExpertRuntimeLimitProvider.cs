namespace LocalAI.CloudInterface;

public sealed class DefaultExpertRuntimeLimitProvider : IExpertRuntimeLimitProvider
{
    public ExpertRuntimeLimit GetLimit(IExpert expert)
    {
        ArgumentNullException.ThrowIfNull(expert);

        if (expert.Profile.Provider.Contains("ollama", StringComparison.OrdinalIgnoreCase))
        {
            return new ExpertRuntimeLimit
            {
                MaxConcurrentRequests = 1,
                Timeout = TimeSpan.FromMinutes(3),
                MaxRetries = 1,
                MinDelayBetweenRequests = TimeSpan.FromMilliseconds(250),
                CircuitBreakerFailureThreshold = 2,
                CircuitBreakerBreakDuration = TimeSpan.FromSeconds(45),
                MaxMemoryMb = expert.Profile.RequiredMemoryMb
            };
        }

        if (expert.Profile.Provider.Contains("openai", StringComparison.OrdinalIgnoreCase)
            || expert.Profile.Provider.Contains("api", StringComparison.OrdinalIgnoreCase))
        {
            return new ExpertRuntimeLimit
            {
                MaxConcurrentRequests = 2,
                Timeout = TimeSpan.FromMinutes(2),
                MaxRetries = 2,
                MinDelayBetweenRequests = TimeSpan.FromMilliseconds(500),
                CircuitBreakerFailureThreshold = 3,
                CircuitBreakerBreakDuration = TimeSpan.FromSeconds(30),
                MaxMemoryMb = expert.Profile.RequiredMemoryMb
            };
        }

        return new ExpertRuntimeLimit
        {
            MaxConcurrentRequests = 4,
            Timeout = TimeSpan.FromMinutes(1),
            MaxRetries = 1,
            CircuitBreakerFailureThreshold = 3,
            CircuitBreakerBreakDuration = TimeSpan.FromSeconds(20),
            MaxMemoryMb = expert.Profile.RequiredMemoryMb
        };
    }
}
