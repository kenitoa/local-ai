namespace LocalAI.CloudInterface;

public sealed class ScoreBasedAggregator : IAggregator
{
    public Task<AggregatedResult> AggregateAsync(
        IReadOnlyList<ExpertResult> results,
        RuntimeContext context)
    {
        ArgumentNullException.ThrowIfNull(results);
        ArgumentNullException.ThrowIfNull(context);

        var minimumConfidence = GetMinimumConfidence(context);
        var candidates = results
            .Select(CreateCandidate)
            .Where(candidate => candidate.Succeeded)
            .Where(candidate => candidate.Confidence >= minimumConfidence)
            .Where(candidate => !string.IsNullOrWhiteSpace(candidate.Output))
            .OrderByDescending(candidate => candidate.Score)
            .ThenByDescending(candidate => candidate.Confidence)
            .ThenBy(candidate => candidate.LatencyMs)
            .ToArray();

        var selected = SelectBestCandidate(candidates);
        var strategy = selected?.IsJudge == true
            ? AggregationStrategy.JudgeSelection
            : AggregationStrategy.WeightedScore;

        var warnings = CollectWarnings(results, candidates, minimumConfidence).ToArray();
        var aggregated = new AggregatedResult
        {
            Output = selected?.Output ?? string.Empty,
            Confidence = selected?.Confidence ?? 0,
            Strategy = strategy,
            SelectedExpertId = selected?.ExpertId,
            UsedExperts = results.Select(result => result.ExpertId)
                .Where(id => !string.IsNullOrWhiteSpace(id))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            Candidates = candidates,
            Warnings = warnings,
            Succeeded = selected is not null,
            Metadata = new Dictionary<string, object>
            {
                ["candidateCount"] = candidates.Length,
                ["rawResultCount"] = results.Count,
                ["minimumConfidence"] = minimumConfidence,
                ["topCandidatesForJudge"] = candidates.Take(3).Select(candidate => candidate.ExpertId).ToArray()
            }
        };

        lock (context)
        {
            context.WorkingMemory["aggregatedResult"] = aggregated;
            context.WorkingMemory["topCandidatesForJudge"] = candidates.Take(3).ToArray();
            context.ExecutionHistory.Add(new ExecutionHistoryEntry
            {
                Step = "Aggregator.Aggregate",
                Actor = nameof(ScoreBasedAggregator),
                OutputSummary = aggregated.Output,
                Succeeded = aggregated.Succeeded,
                Metadata = new Dictionary<string, object>
                {
                    ["strategy"] = aggregated.Strategy,
                    ["selectedExpertId"] = aggregated.SelectedExpertId ?? string.Empty,
                    ["confidence"] = aggregated.Confidence
                }
            });
        }

        return Task.FromResult(aggregated);
    }

    private static AggregationCandidate? SelectBestCandidate(IReadOnlyList<AggregationCandidate> candidates)
    {
        var judgeCandidate = candidates
            .Where(candidate => candidate.IsJudge)
            .OrderByDescending(candidate => candidate.Score)
            .FirstOrDefault();

        return judgeCandidate ?? candidates.FirstOrDefault();
    }

    private static AggregationCandidate CreateCandidate(ExpertResult result)
    {
        var latencyMs = result.LatencyMs > 0 ? result.LatencyMs : result.Duration.TotalMilliseconds;
        var isJudge = IsJudgeResult(result);
        var score = CalculateScore(result, latencyMs, isJudge);

        return new AggregationCandidate
        {
            ExpertId = result.ExpertId,
            Output = result.Output,
            Confidence = result.Confidence,
            Score = score,
            LatencyMs = latencyMs,
            IsJudge = isJudge,
            Succeeded = result.Succeeded,
            Warnings = result.Warnings,
            Metadata = result.Metadata
        };
    }

    private static double CalculateScore(ExpertResult result, double latencyMs, bool isJudge)
    {
        var confidenceScore = Clamp(result.Confidence);
        var latencyScore = latencyMs <= 0 ? 1.0 : 1.0 / (1.0 + latencyMs / 10_000.0);
        var warningPenalty = Math.Min(0.3, result.Warnings.Length * 0.05);
        var jsonBonus = result.IsJsonOutput ? 0.03 : 0.0;
        var judgeBonus = isJudge ? 0.08 : 0.0;

        return Clamp(confidenceScore * 0.72 + latencyScore * 0.2 + jsonBonus + judgeBonus - warningPenalty);
    }

    private static IEnumerable<string> CollectWarnings(
        IReadOnlyList<ExpertResult> results,
        IReadOnlyList<AggregationCandidate> candidates,
        double minimumConfidence)
    {
        foreach (var result in results)
        {
            foreach (var warning in result.Warnings)
            {
                yield return $"{result.ExpertId}: {warning}";
            }

            if (!result.Succeeded)
            {
                yield return $"{result.ExpertId}: failed{(string.IsNullOrWhiteSpace(result.Error) ? string.Empty : $" - {result.Error}")}";
            }
            else if (result.Confidence < minimumConfidence)
            {
                yield return $"{result.ExpertId}: confidence below threshold";
            }
        }

        if (candidates.Count == 0)
        {
            yield return "No expert result passed aggregation filters.";
        }
    }

    private static double GetMinimumConfidence(RuntimeContext context)
    {
        if (context.WorkingMemory.TryGetValue("runtimeOptions", out var value)
            && value is RuntimeOptions options)
        {
            return Clamp(options.MinimumConfidence);
        }

        return 0.0;
    }

    private static bool IsJudgeResult(ExpertResult result)
    {
        return result.ExpertId.Contains("judge", StringComparison.OrdinalIgnoreCase)
            || result.Metadata.TryGetValue("modelType", out var modelType)
            && string.Equals(modelType?.ToString(), "judge", StringComparison.OrdinalIgnoreCase);
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
