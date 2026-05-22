namespace LocalAI.CloudInterface;

public sealed class ExpertScorer
{
    private readonly IExpertHistoryProvider historyProvider;

    public ExpertScorer(IExpertHistoryProvider? historyProvider = null)
    {
        this.historyProvider = historyProvider ?? new TraceExpertHistoryProvider();
    }

    public ExpertScore Score(IExpert expert, CloudAIRequest request, string capability)
    {
        ArgumentNullException.ThrowIfNull(expert);
        ArgumentNullException.ThrowIfNull(request);

        var stats = historyProvider.GetStats(expert.Id);
        var capabilityMatch = CalculateCapabilityMatch(expert.Profile, capability, request);
        var qualityScore = Clamp(expert.Profile.QualityScore);
        var successRate = Clamp(stats.SuccessRate);
        var latencyPenalty = CalculateLatencyPenalty(expert.Profile, stats);
        var costPenalty = 1.0 - Clamp(expert.Profile.CostScore);
        var memoryPenalty = CalculateMemoryPenalty(expert.Profile);

        var totalScore =
            capabilityMatch * 0.35
            + qualityScore * 0.30
            + successRate * 0.20
            - latencyPenalty * 0.10
            - costPenalty * 0.05
            - memoryPenalty * 0.05;

        return new ExpertScore
        {
            ExpertId = expert.Id,
            CapabilityMatch = capabilityMatch,
            QualityScore = qualityScore,
            SuccessRate = successRate,
            LatencyPenalty = latencyPenalty,
            CostPenalty = costPenalty,
            MemoryPenalty = memoryPenalty,
            TotalScore = Clamp(totalScore),
            Metadata = new Dictionary<string, object>
            {
                ["capability"] = capability,
                ["totalRuns"] = stats.TotalRuns,
                ["successfulRuns"] = stats.SuccessfulRuns,
                ["averageLatencyMs"] = stats.AverageLatencyMs
            }
        };
    }

    private static double CalculateCapabilityMatch(ExpertProfile profile, string capability, CloudAIRequest request)
    {
        if (string.IsNullOrWhiteSpace(capability))
        {
            return profile.ModelType.Equals("llm", StringComparison.OrdinalIgnoreCase) ? 0.65 : 0.45;
        }

        if (profile.Capabilities.Any(item => item.Equals(capability, StringComparison.OrdinalIgnoreCase)))
        {
            return 1.0;
        }

        if (profile.ModelType.Equals(capability, StringComparison.OrdinalIgnoreCase))
        {
            return 0.9;
        }

        if (request.TaskType is not null && profile.Capabilities.Any(item => item.Equals(request.TaskType, StringComparison.OrdinalIgnoreCase)))
        {
            return 0.85;
        }

        return profile.ModelType.Equals("llm", StringComparison.OrdinalIgnoreCase) ? 0.55 : 0.2;
    }

    private static double CalculateLatencyPenalty(ExpertProfile profile, ExpertHistoricalStats stats)
    {
        if (stats.AverageLatencyMs > 0)
        {
            return Clamp(stats.AverageLatencyMs / 20_000.0);
        }

        return 1.0 - Clamp(profile.LatencyScore);
    }

    private static double CalculateMemoryPenalty(ExpertProfile profile)
    {
        return profile.RequiredMemoryMb <= 0
            ? 0
            : Clamp(profile.RequiredMemoryMb / 16_384.0);
    }

    private static double Clamp(double value)
    {
        if (double.IsNaN(value) || double.IsInfinity(value))
        {
            return 0;
        }

        return Math.Max(0, Math.Min(1, value));
    }
}
