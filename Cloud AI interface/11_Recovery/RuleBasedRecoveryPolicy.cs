using System.Text.Json;

namespace LocalAI.CloudInterface;

public sealed class RuleBasedRecoveryPolicy : IRecoveryPolicy
{
    private readonly IReadOnlyList<FallbackChainProfile> fallbackChains;

    public RuleBasedRecoveryPolicy(IReadOnlyList<FallbackChainProfile>? fallbackChains = null)
    {
        this.fallbackChains = fallbackChains ?? Array.Empty<FallbackChainProfile>();
    }

    public Task<RecoveryDecision> CreateRecoveryAsync(RecoveryInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        var failureType = DetectFailure(input);
        var decision = failureType switch
        {
            FailureType.ExpertTimeout => CreateFallbackDecision(input, failureType, RecoveryAction.UseFallbackModel, "Expert timed out; use a lighter fallback model."),
            FailureType.ModelUnavailable => CreateFallbackDecision(input, failureType, RecoveryAction.UseFallbackModel, "Model is unavailable; move to fallback chain."),
            FailureType.InvalidJson => CreateRepairJsonDecision(input),
            FailureType.LowConfidence => CreateFallbackDecision(input, failureType, RecoveryAction.AddExpertAndRetry, "Confidence is too low; add another expert and retry."),
            FailureType.ContradictoryAnswers => CreateRejudgeDecision(input),
            FailureType.OutOfMemory => CreateFallbackDecision(input, failureType, RecoveryAction.UnloadModelAndFallback, "Memory pressure detected; unload heavy model and fallback.", requiresModelUnload: true),
            FailureType.RateLimit => CreateBackoffDecision(input),
            _ => new RecoveryDecision
            {
                ShouldRecover = false,
                FailureType = FailureType.Unknown,
                Action = RecoveryAction.Stop,
                Reason = "No recoverable failure was detected."
            }
        };

        lock (input.Context)
        {
            input.Context.WorkingMemory["recoveryDecision"] = decision;
            input.Context.ExecutionHistory.Add(new ExecutionHistoryEntry
            {
                Step = "Recovery.Decide",
                Actor = nameof(RuleBasedRecoveryPolicy),
                OutputSummary = $"{decision.FailureType}:{decision.Action}",
                Succeeded = decision.ShouldRecover,
                Metadata = new Dictionary<string, object>
                {
                    ["failureType"] = decision.FailureType,
                    ["action"] = decision.Action,
                    ["fallbackExpertIds"] = decision.FallbackExpertIds
                }
            });
        }

        return Task.FromResult(decision);
    }

    private static string DetectFailure(RecoveryInput input)
    {
        if (input.ExpertResults.Any(result => ContainsAny(result.Error, "timeout", "timed out")))
        {
            return FailureType.ExpertTimeout;
        }

        if (input.ExpertResults.Any(result => ContainsAny(result.Error, "unavailable", "not registered", "not configured", "missing")))
        {
            return FailureType.ModelUnavailable;
        }

        if (input.ExpertResults.Any(result => ContainsAny(result.Error, "out of memory", "oom", "vram", "ram", "memory limit")))
        {
            return FailureType.OutOfMemory;
        }

        if (input.ExpertResults.Any(result => ContainsAny(result.Error, "rate limit", "429", "too many requests", "circuit breaker", "concurrency")))
        {
            return FailureType.RateLimit;
        }

        if (RequiresJson(input) && !IsJson(input.AggregatedResult?.Output))
        {
            return FailureType.InvalidJson;
        }

        if (input.VerifiedResult?.Conflicts.Count > 0)
        {
            return FailureType.ContradictoryAnswers;
        }

        if (input.VerifiedResult?.NeedsRetry == true
            || input.AggregatedResult?.Succeeded == false
            || input.AggregatedResult?.Confidence < input.Request.Options.MinimumConfidence)
        {
            return FailureType.LowConfidence;
        }

        return FailureType.Unknown;
    }

    private RecoveryDecision CreateFallbackDecision(
        RecoveryInput input,
        string failureType,
        string action,
        string reason,
        bool requiresModelUnload = false)
    {
        var fallbackExpertIds = SelectFallbackExpertIds(input).ToArray();
        return new RecoveryDecision
        {
            ShouldRecover = fallbackExpertIds.Length > 0,
            FailureType = failureType,
            Action = fallbackExpertIds.Length > 0 ? action : RecoveryAction.Stop,
            Reason = fallbackExpertIds.Length > 0 ? reason : "No fallback expert is available.",
            FallbackExpertIds = fallbackExpertIds,
            RetryPlan = fallbackExpertIds.Length > 0 ? CreateFallbackPlan(input.Plan, fallbackExpertIds, failureType) : null,
            RequiresModelUnload = requiresModelUnload,
            Metadata = new Dictionary<string, object>
            {
                ["primaryPlanId"] = input.Plan.PlanId
            }
        };
    }

    private RecoveryDecision CreateRepairJsonDecision(RecoveryInput input)
    {
        var prompt = "Repair the previous answer into valid JSON only. Preserve the meaning and remove non-JSON text.";
        var fallbackExpertIds = SelectFallbackExpertIds(input).ToArray();
        return new RecoveryDecision
        {
            ShouldRecover = true,
            FailureType = FailureType.InvalidJson,
            Action = RecoveryAction.RepairPrompt,
            Reason = "Expected JSON output was invalid.",
            RepairPrompt = prompt,
            FallbackExpertIds = fallbackExpertIds,
            RetryPlan = CreateFallbackPlan(input.Plan, fallbackExpertIds, FailureType.InvalidJson, prompt)
        };
    }

    private RecoveryDecision CreateRejudgeDecision(RecoveryInput input)
    {
        var judgeExpertIds = input.AvailableExperts
            .Where(expert => expert.Profile.ModelType.Equals("judge", StringComparison.OrdinalIgnoreCase)
                || expert.Profile.Capabilities.Any(capability => capability.Equals("judge", StringComparison.OrdinalIgnoreCase)))
            .Select(expert => expert.Id)
            .ToArray();

        return new RecoveryDecision
        {
            ShouldRecover = judgeExpertIds.Length > 0,
            FailureType = FailureType.ContradictoryAnswers,
            Action = judgeExpertIds.Length > 0 ? RecoveryAction.Rejudge : RecoveryAction.Stop,
            Reason = judgeExpertIds.Length > 0 ? "Contradictory answers require judge revalidation." : "No judge expert is available.",
            FallbackExpertIds = judgeExpertIds,
            RetryPlan = judgeExpertIds.Length > 0 ? CreateFallbackPlan(input.Plan, judgeExpertIds, FailureType.ContradictoryAnswers) : null
        };
    }

    private RecoveryDecision CreateBackoffDecision(RecoveryInput input)
    {
        var fallbackExpertIds = SelectFallbackExpertIds(input).ToArray();
        var delay = TimeSpan.FromSeconds(2);
        return new RecoveryDecision
        {
            ShouldRecover = true,
            FailureType = FailureType.RateLimit,
            Action = RecoveryAction.BackoffAndRetry,
            Reason = "Rate limit or circuit breaker detected; wait before retrying.",
            Delay = delay,
            FallbackExpertIds = fallbackExpertIds,
            RetryPlan = CreateFallbackPlan(input.Plan, fallbackExpertIds.Length > 0 ? fallbackExpertIds : input.Plan.Steps.Select(step => step.ExpertId).ToArray(), FailureType.RateLimit),
            Metadata = new Dictionary<string, object>
            {
                ["delayMs"] = delay.TotalMilliseconds
            }
        };
    }

    private IEnumerable<string> SelectFallbackExpertIds(RecoveryInput input)
    {
        var failedExpertIds = input.ExpertResults
            .Where(result => !result.Succeeded || !string.IsNullOrWhiteSpace(result.Error))
            .Select(result => result.ExpertId)
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        var explicitFallbacks = input.Plan.Metadata.TryGetValue("fallback", out var fallbackValue)
            ? ToStringSequence(fallbackValue)
            : Array.Empty<string>();

        foreach (var id in explicitFallbacks)
        {
            yield return id;
        }

        foreach (var id in fallbackChains
            .Where(chain => failedExpertIds.Contains(chain.Primary))
            .SelectMany(chain => chain.Fallback))
        {
            yield return id;
        }

        foreach (var id in input.AvailableExperts
            .Where(expert => !failedExpertIds.Contains(expert.Id))
            .OrderBy(expert => expert.Profile.Priority)
            .ThenByDescending(expert => expert.Profile.QualityScore)
            .Select(expert => expert.Id))
        {
            yield return id;
        }

        yield return "rule-based-response";
    }

    private static ExecutionPlan CreateFallbackPlan(
        ExecutionPlan originalPlan,
        IReadOnlyList<string> fallbackExpertIds,
        string failureType,
        string? repairPrompt = null)
    {
        var distinctFallbacks = fallbackExpertIds
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return new ExecutionPlan
        {
            Steps = distinctFallbacks.Select((expertId, index) => new ExecutionStep
            {
                Order = index + 1,
                ExpertId = expertId,
                Role = "recovery-fallback",
                Reason = failureType,
                CanRunInParallel = false,
                DependsOnExpertIds = index == 0 ? Array.Empty<string>() : [distinctFallbacks[index - 1]],
                Metadata = repairPrompt is null
                    ? new Dictionary<string, object>()
                    : new Dictionary<string, object> { ["repairPrompt"] = repairPrompt }
            }).ToList(),
            RequiresJudge = failureType == FailureType.ContradictoryAnswers,
            RunInParallel = false,
            Metadata = new Dictionary<string, object>
            {
                ["recoveryForPlanId"] = originalPlan.PlanId,
                ["failureType"] = failureType
            }
        };
    }

    private static bool RequiresJson(RecoveryInput input)
    {
        return input.Plan.Steps.Any(step =>
                step.Metadata.TryGetValue("expectedOutputFormat", out var value)
                && string.Equals(value?.ToString(), "json", StringComparison.OrdinalIgnoreCase))
            || input.AggregatedResult?.Metadata.TryGetValue("expectedOutputFormat", out var outputFormat) == true
            && string.Equals(outputFormat?.ToString(), "json", StringComparison.OrdinalIgnoreCase)
            || input.ExpertResults.Any(result => result.IsJsonOutput);
    }

    private static bool IsJson(string? value)
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

    private static bool ContainsAny(string? value, params string[] needles)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return needles.Any(needle => value.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }

    private static IReadOnlyList<string> ToStringSequence(object value)
    {
        return value switch
        {
            string single => [single],
            IEnumerable<string> strings => strings.ToArray(),
            _ => Array.Empty<string>()
        };
    }
}
