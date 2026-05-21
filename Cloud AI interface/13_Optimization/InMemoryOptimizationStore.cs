using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryOptimizationStore : IOptimizationStore
{
    private readonly ConcurrentQueue<OptimizationRecord> records = new();

    public Task AddAsync(OptimizationRecord record)
    {
        ArgumentNullException.ThrowIfNull(record);

        records.Enqueue(record);
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<OptimizationRecord>> GetByInputTypeAsync(string inputType)
    {
        var matches = records
            .Where(record => string.Equals(record.InputType, inputType, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(record => record.CreatedAt)
            .ToArray();

        return Task.FromResult<IReadOnlyList<OptimizationRecord>>(matches);
    }

    public Task<IReadOnlyList<CompositionPerformanceStats>> GetStatsAsync(string inputType)
    {
        var matches = records
            .Where(record => string.Equals(record.InputType, inputType, StringComparison.OrdinalIgnoreCase))
            .ToArray();

        var stats = matches
            .GroupBy(GetCompositionKey, StringComparer.OrdinalIgnoreCase)
            .Select(group => CreateStats(inputType, group))
            .OrderByDescending(stat => stat.PerformanceScore)
            .ThenBy(stat => stat.AverageLatencyMs)
            .ToArray();

        return Task.FromResult<IReadOnlyList<CompositionPerformanceStats>>(stats);
    }

    private static string GetCompositionKey(OptimizationRecord record)
    {
        return !string.IsNullOrWhiteSpace(record.SelectedComposition)
            ? record.SelectedComposition
            : string.Join("+", record.ExpertCombination);
    }

    private static CompositionPerformanceStats CreateStats(
        string inputType,
        IGrouping<string, OptimizationRecord> group)
    {
        var items = group.ToArray();
        var failedRuns = items.LongCount(item => item.Failed);
        var feedbackItems = items.Where(item => item.UserFeedback is not null).ToArray();
        var acceptanceCount = feedbackItems.LongCount(item => item.UserFeedback?.Accepted == true);
        var averageJudgeScore = items.Average(item => item.JudgeScore);
        var averageUserRating = feedbackItems.Length == 0 ? 0.5 : feedbackItems.Average(item => Clamp(item.UserFeedback?.Rating ?? 0));
        var acceptanceRate = feedbackItems.Length == 0 ? 0.5 : (double)acceptanceCount / feedbackItems.Length;
        var failureRate = items.Length == 0 ? 1.0 : (double)failedRuns / items.Length;
        var averageLatencyMs = items.Average(item => item.LatencyMs);
        var averageCost = items.Average(item => item.EstimatedCost);
        var latencyPenalty = averageLatencyMs <= 0 ? 0 : Clamp(averageLatencyMs / 30_000.0);
        var costPenalty = averageCost <= 0 ? 0 : Clamp(averageCost);
        var performanceScore = Clamp(
            averageJudgeScore * 0.38
            + averageUserRating * 0.24
            + acceptanceRate * 0.18
            - failureRate * 0.12
            - latencyPenalty * 0.05
            - costPenalty * 0.03);

        return new CompositionPerformanceStats
        {
            InputType = inputType,
            CompositionId = group.Key,
            ExpertCombination = items.FirstOrDefault()?.ExpertCombination ?? Array.Empty<string>(),
            TotalRuns = items.Length,
            FailedRuns = failedRuns,
            FailureRate = failureRate,
            AverageJudgeScore = averageJudgeScore,
            AverageUserRating = averageUserRating,
            AcceptanceRate = acceptanceRate,
            AverageLatencyMs = averageLatencyMs,
            AverageCost = averageCost,
            PerformanceScore = performanceScore
        };
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
