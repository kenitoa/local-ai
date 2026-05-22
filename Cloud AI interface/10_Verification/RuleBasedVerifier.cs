using System.Text.Json;

namespace LocalAI.CloudInterface;

public sealed class RuleBasedVerifier : IVerifier
{
    private const double RetryThreshold = 0.62;

    public Task<VerifiedResult> VerifyAsync(
        AggregatedResult result,
        RuntimeContext context)
    {
        ArgumentNullException.ThrowIfNull(result);
        ArgumentNullException.ThrowIfNull(context);

        var scores = CreateScores(result, context).ToArray();
        var weightedScore = CalculateWeightedScore(scores);
        var conflicts = DetectConflicts(result).ToArray();
        var warnings = result.Warnings.Concat(CreateVerifierWarnings(result, conflicts, weightedScore)).Distinct().ToArray();
        var needsRetry = !result.Succeeded
            || weightedScore < RetryThreshold
            || conflicts.Length > 0
            || string.IsNullOrWhiteSpace(result.Output);

        var verified = new VerifiedResult
        {
            WinnerExpertId = result.SelectedExpertId ?? string.Empty,
            Score = weightedScore,
            Reason = CreateReason(scores, conflicts, needsRetry),
            FinalAnswer = needsRetry ? string.Empty : result.Output,
            NeedsRetry = needsRetry,
            Scores = scores,
            Conflicts = conflicts,
            Warnings = warnings,
            Metadata = new Dictionary<string, object>
            {
                ["judgeOutputJson"] = CreateJudgeJson(result, weightedScore, needsRetry, scores, conflicts),
                ["candidateCount"] = result.Candidates.Count,
                ["strategy"] = result.Strategy
            }
        };

        lock (context)
        {
            context.WorkingMemory["verifiedResult"] = verified;
            context.ExecutionHistory.Add(new ExecutionHistoryEntry
            {
                Step = "Verifier.Verify",
                Actor = nameof(RuleBasedVerifier),
                InputSummary = result.Output,
                OutputSummary = verified.FinalAnswer,
                Succeeded = !verified.NeedsRetry,
                Metadata = new Dictionary<string, object>
                {
                    ["winnerExpertId"] = verified.WinnerExpertId,
                    ["score"] = verified.Score,
                    ["needsRetry"] = verified.NeedsRetry
                }
            });
        }

        return Task.FromResult(verified);
    }

    private static IEnumerable<VerificationScore> CreateScores(AggregatedResult result, RuntimeContext context)
    {
        yield return Score(VerificationCriteria.Correctness, result.Confidence, 0.24, "based on selected expert confidence");
        yield return Score(VerificationCriteria.Completeness, ScoreCompleteness(result, context), 0.18, "checks answer coverage and non-empty output");
        yield return Score(VerificationCriteria.Consistency, ScoreConsistency(result), 0.14, "compares candidate outputs for conflict signs");
        yield return Score(VerificationCriteria.Safety, ScoreSafety(result), 0.14, "penalizes unsafe or failed outputs");
        yield return Score(VerificationCriteria.InstructionFollowing, ScoreInstructionFollowing(result, context), 0.12, "checks task and format alignment");
        yield return Score(VerificationCriteria.FormatValidity, ScoreFormatValidity(result), 0.08, "checks requested structured output validity");
        yield return Score(VerificationCriteria.SourceReliability, ScoreSourceReliability(result), 0.06, "uses candidate count and warnings as reliability signals");
        yield return Score(VerificationCriteria.LatencyCost, ScoreLatencyCost(result), 0.04, "penalizes high latency candidates");
    }

    private static VerificationScore Score(string criterion, double score, double weight, string reason)
    {
        return new VerificationScore
        {
            Criterion = criterion,
            Score = Clamp(score),
            Weight = weight,
            Reason = reason
        };
    }

    private static double CalculateWeightedScore(IEnumerable<VerificationScore> scores)
    {
        var scoreList = scores.ToArray();
        var totalWeight = scoreList.Sum(score => score.Weight);
        return totalWeight <= 0
            ? 0
            : Clamp(scoreList.Sum(score => score.Score * score.Weight) / totalWeight);
    }

    private static double ScoreCompleteness(AggregatedResult result, RuntimeContext context)
    {
        if (string.IsNullOrWhiteSpace(result.Output))
        {
            return 0;
        }

        var userGoal = context.TaskState.Goal
            ?? context.Conversation.LastOrDefault(message => message.Role.Equals("user", StringComparison.OrdinalIgnoreCase))?.Content
            ?? string.Empty;

        var answerLength = result.Output.Trim().Length;
        var baseline = answerLength switch
        {
            < 20 => 0.45,
            < 80 => 0.72,
            _ => 0.92
        };

        return string.IsNullOrWhiteSpace(userGoal) ? baseline : Math.Min(1, baseline + 0.05);
    }

    private static double ScoreConsistency(AggregatedResult result)
    {
        if (result.Candidates.Count <= 1)
        {
            return 0.78;
        }

        var conflicts = DetectConflicts(result).Count();
        return conflicts == 0 ? 0.9 : Math.Max(0.25, 0.9 - conflicts * 0.18);
    }

    private static double ScoreSafety(AggregatedResult result)
    {
        if (!result.Succeeded)
        {
            return 0.2;
        }

        var output = result.Output.ToLowerInvariant();
        var unsafeSignals = new[] { "password", "secret", "api key", "token", "credential" };
        return unsafeSignals.Any(output.Contains) ? 0.45 : 0.94;
    }

    private static double ScoreInstructionFollowing(AggregatedResult result, RuntimeContext context)
    {
        if (!result.Succeeded || string.IsNullOrWhiteSpace(result.Output))
        {
            return 0.2;
        }

        var taskType = context.WorkingMemory.TryGetValue("taskType", out var value) ? value?.ToString() : null;
        if (string.IsNullOrWhiteSpace(taskType))
        {
            return 0.82;
        }

        return result.Metadata.TryGetValue("taskType", out var resultTaskType)
            && string.Equals(resultTaskType?.ToString(), taskType, StringComparison.OrdinalIgnoreCase)
            ? 0.95
            : 0.78;
    }

    private static double ScoreFormatValidity(AggregatedResult result)
    {
        if (result.Metadata.TryGetValue("expectedOutputFormat", out var format)
            && string.Equals(format?.ToString(), "json", StringComparison.OrdinalIgnoreCase))
        {
            return IsJson(result.Output) ? 1.0 : 0.35;
        }

        return string.IsNullOrWhiteSpace(result.Output) ? 0 : 0.9;
    }

    private static double ScoreSourceReliability(AggregatedResult result)
    {
        var candidateBonus = Math.Min(0.2, result.Candidates.Count * 0.05);
        var warningPenalty = Math.Min(0.4, result.Warnings.Count * 0.06);
        return Clamp(0.72 + candidateBonus - warningPenalty);
    }

    private static double ScoreLatencyCost(AggregatedResult result)
    {
        if (result.Candidates.Count == 0)
        {
            return 0.5;
        }

        var averageLatency = result.Candidates.Average(candidate => candidate.LatencyMs);
        return averageLatency <= 0 ? 0.9 : Clamp(1.0 / (1.0 + averageLatency / 15_000.0));
    }

    private static IEnumerable<string> DetectConflicts(AggregatedResult result)
    {
        var normalizedOutputs = result.Candidates
            .Select(candidate => Normalize(candidate.Output))
            .Where(output => output.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        if (normalizedOutputs.Length > 1 && result.Candidates.Count(candidate => candidate.Confidence >= 0.7) > 1)
        {
            yield return "High-confidence expert outputs are not identical.";
        }

    }

    private static IEnumerable<string> CreateVerifierWarnings(
        AggregatedResult result,
        IReadOnlyList<string> conflicts,
        double weightedScore)
    {
        if (conflicts.Count > 0)
        {
            yield return "Conflicts need judge review or retry.";
        }

        if (weightedScore < RetryThreshold)
        {
            yield return "Verification score is below retry threshold.";
        }

        if (string.IsNullOrWhiteSpace(result.Output))
        {
            yield return "Final answer is empty.";
        }
    }

    private static string CreateReason(
        IReadOnlyList<VerificationScore> scores,
        IReadOnlyList<string> conflicts,
        bool needsRetry)
    {
        var strongest = scores.OrderByDescending(score => score.Score * score.Weight).FirstOrDefault();
        var weakest = scores.OrderBy(score => score.Score).FirstOrDefault();

        if (needsRetry)
        {
            return conflicts.Count > 0
                ? "Conflicts were detected between expert outputs."
                : $"Lowest score: {weakest?.Criterion ?? "unknown"}.";
        }

        return $"Best supported by {strongest?.Criterion ?? "weighted verification"}.";
    }

    private static string CreateJudgeJson(
        AggregatedResult result,
        double score,
        bool needsRetry,
        IReadOnlyList<VerificationScore> scores,
        IReadOnlyList<string> conflicts)
    {
        var payload = new
        {
            winnerExpertId = result.SelectedExpertId ?? string.Empty,
            score,
            reason = conflicts.Count > 0 ? "conflicts detected" : "weighted criteria passed",
            finalAnswer = needsRetry ? string.Empty : result.Output,
            needsRetry,
            scores = scores.Select(item => new
            {
                criterion = item.Criterion,
                score = item.Score,
                weight = item.Weight,
                reason = item.Reason
            }),
            conflicts
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true });
    }

    private static bool IsJson(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        try
        {
            using var _ = JsonDocument.Parse(value);
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static string Normalize(string value)
    {
        return string.Join(' ', value.Trim().Split(Array.Empty<char>(), StringSplitOptions.RemoveEmptyEntries));
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
