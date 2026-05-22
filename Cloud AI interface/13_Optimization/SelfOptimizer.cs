namespace LocalAI.CloudInterface;

public sealed class SelfOptimizer : ISelfOptimizer
{
    private readonly IOptimizationStore store;

    public SelfOptimizer(IOptimizationStore? store = null)
    {
        this.store = store ?? new InMemoryOptimizationStore();
    }

    public async Task RecordAsync(RequestTrace trace, UserFeedback? feedback = null)
    {
        ArgumentNullException.ThrowIfNull(trace);

        var record = new OptimizationRecord
        {
            RequestId = trace.RequestId,
            InputType = DetectInputType(trace),
            SelectedComposition = trace.Composition,
            ExpertCombination = trace.SelectedExperts,
            JudgeScore = trace.JudgeScore,
            UserFeedback = feedback,
            LatencyMs = trace.LatencyMs,
            EstimatedCost = EstimateCost(trace),
            Failed = trace.Error,
            CreatedAt = trace.CreatedAt,
            Metadata = new Dictionary<string, object>
            {
                ["fallbackUsed"] = trace.FallbackUsed,
                ["tokenUsage"] = trace.TokenUsage.TotalTokens,
                ["memoryMb"] = trace.MemoryUsage.EstimatedUsedMemoryMb
            }
        };

        await store.AddAsync(record).ConfigureAwait(false);
    }

    public async Task<OptimizationRecommendation> RecommendAsync(CloudAIRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var inputType = DetectInputType(request);
        var stats = await store.GetStatsAsync(inputType).ConfigureAwait(false);
        var best = stats.FirstOrDefault(stat => stat.TotalRuns >= 1 && stat.PerformanceScore > 0);

        if (best is null)
        {
            return new OptimizationRecommendation
            {
                InputType = inputType,
                Score = 0,
                Reason = "No historical composition data is available."
            };
        }

        return new OptimizationRecommendation
        {
            InputType = inputType,
            CompositionId = best.CompositionId,
            ExpertCombination = best.ExpertCombination,
            Score = best.PerformanceScore,
            Stats = best,
            Reason = $"Selected from {best.TotalRuns} previous runs with failure rate {best.FailureRate:0.###}."
        };
    }

    private static string DetectInputType(RequestTrace trace)
    {
        if (trace.Metadata.TryGetValue("inputType", out var inputType)
            && !string.IsNullOrWhiteSpace(inputType?.ToString()))
        {
            return inputType.ToString()!;
        }

        if (!string.IsNullOrWhiteSpace(trace.Composition))
        {
            return trace.Composition.Contains("code", StringComparison.OrdinalIgnoreCase)
                ? "code"
                : trace.Composition.Contains("reasoning", StringComparison.OrdinalIgnoreCase)
                    ? "reasoning"
                    : "chat";
        }

        return trace.SelectedExperts.Any(expert => expert.Contains("code", StringComparison.OrdinalIgnoreCase))
            ? "code"
            : "chat";
    }

    private static string DetectInputType(CloudAIRequest request)
    {
        var taskType = request.TaskType?.Trim().ToLowerInvariant();
        var input = request.Input.ToLowerInvariant();

        if (!string.IsNullOrWhiteSpace(taskType))
        {
            return taskType;
        }

        if (ContainsAny(input, "코드", "최적화", "버그", "refactor", "optimize", "bug", "code"))
        {
            return "code";
        }

        if (ContainsAny(input, "이미지", "사진", "화면", "image", "vision", "screenshot"))
        {
            return "vision";
        }

        if (ContainsAny(input, "분류", "classify", "classification", "intent"))
        {
            return "classify";
        }

        return "chat";
    }

    private static double EstimateCost(RequestTrace trace)
    {
        var tokenCost = trace.TokenUsage.TotalTokens / 100_000.0;
        var memoryCost = trace.MemoryUsage.EstimatedUsedMemoryMb / 65_536.0;
        var fallbackPenalty = trace.FallbackUsed ? 0.05 : 0;
        return Clamp(tokenCost + memoryCost + fallbackPenalty);
    }

    private static bool ContainsAny(string input, params string[] needles)
    {
        return needles.Any(needle => input.Contains(needle, StringComparison.OrdinalIgnoreCase));
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
