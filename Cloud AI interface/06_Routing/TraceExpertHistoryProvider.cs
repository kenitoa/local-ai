namespace LocalAI.CloudInterface;

public sealed class TraceExpertHistoryProvider : IExpertHistoryProvider
{
    private readonly IReadOnlyList<RequestTrace> traces;

    public TraceExpertHistoryProvider(IReadOnlyList<RequestTrace>? traces = null)
    {
        this.traces = traces ?? Array.Empty<RequestTrace>();
    }

    public ExpertHistoricalStats GetStats(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId))
        {
            return new ExpertHistoricalStats();
        }

        var outputs = traces
            .SelectMany(trace => trace.ExpertOutputs.Select(output => new { trace, output }))
            .Where(item => string.Equals(item.output.ExpertId, expertId, StringComparison.OrdinalIgnoreCase))
            .ToArray();

        if (outputs.Length == 0)
        {
            return new ExpertHistoricalStats
            {
                ExpertId = expertId,
                SuccessRate = 0.5
            };
        }

        var successes = outputs.Count(item => item.output.Succeeded && !item.trace.Error);

        return new ExpertHistoricalStats
        {
            ExpertId = expertId,
            TotalRuns = outputs.Length,
            SuccessfulRuns = successes,
            SuccessRate = (double)successes / outputs.Length,
            AverageLatencyMs = outputs.Average(item => item.output.LatencyMs),
            AverageJudgeScore = outputs.Average(item => item.trace.JudgeScore)
        };
    }
}
