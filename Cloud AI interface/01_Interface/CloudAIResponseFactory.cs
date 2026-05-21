namespace LocalAI.CloudInterface;

public static class CloudAIResponseFactory
{
    public static CloudAIResponse FromVerifiedResult(
        VerifiedResult verified,
        AggregatedResult aggregated,
        RuntimeContext context)
    {
        ArgumentNullException.ThrowIfNull(verified);
        ArgumentNullException.ThrowIfNull(aggregated);
        ArgumentNullException.ThrowIfNull(context);

        return new CloudAIResponse
        {
            Output = verified.FinalAnswer,
            Confidence = verified.Score,
            UsedExperts = aggregated.UsedExperts,
            Trace = context.ExecutionHistory.Select(ToTrace).ToArray(),
            Metadata = new Dictionary<string, object>
            {
                ["winnerExpertId"] = verified.WinnerExpertId,
                ["needsRetry"] = verified.NeedsRetry,
                ["verificationReason"] = verified.Reason,
                ["verificationScores"] = verified.Scores,
                ["warnings"] = verified.Warnings
            }
        };
    }

    private static ExpertTrace ToTrace(ExecutionHistoryEntry entry)
    {
        return new ExpertTrace
        {
            ExpertName = entry.Actor,
            Stage = entry.Step,
            InputSummary = entry.InputSummary,
            OutputSummary = entry.OutputSummary,
            Confidence = entry.Metadata.TryGetValue("score", out var score) && score is double numericScore ? numericScore : 0,
            Duration = entry.Duration,
            Succeeded = entry.Succeeded,
            Metadata = entry.Metadata
        };
    }
}
