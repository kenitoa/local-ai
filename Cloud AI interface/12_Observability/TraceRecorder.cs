namespace LocalAI.CloudInterface;

public sealed class TraceRecorder : ITraceRecorder
{
    private readonly IReadOnlyList<ITraceSink> sinks;

    public TraceRecorder(IReadOnlyList<ITraceSink>? sinks = null)
    {
        this.sinks = sinks ?? Array.Empty<ITraceSink>();
    }

    public async Task<RequestTrace> RecordAsync(TraceRecordInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        var trace = CreateTrace(input);
        foreach (var sink in sinks)
        {
            await sink.WriteAsync(trace).ConfigureAwait(false);
        }

        lock (input.Context)
        {
            input.Context.WorkingMemory["lastRequestTrace"] = trace;
        }

        return trace;
    }

    private static RequestTrace CreateTrace(TraceRecordInput input)
    {
        var selectedExperts = (input.Plan?.Steps.Select(step => step.ExpertId) ?? Array.Empty<string>())
            .Concat(input.RecoveryDecision?.RetryPlan?.Steps.Select(step => step.ExpertId) ?? Array.Empty<string>())
            .Concat(input.ExpertResults.Select(result => result.ExpertId))
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        var errors = input.ExpertResults
            .Where(result => !string.IsNullOrWhiteSpace(result.Error))
            .Select(result => $"{result.ExpertId}: {result.Error}")
            .Concat(input.VerifiedResult?.Warnings ?? Array.Empty<string>())
            .Concat(input.RecoveryDecision?.Reason is { Length: > 0 } reason && input.RecoveryDecision.ShouldRecover ? [$"recovery: {reason}"] : [])
            .Distinct()
            .ToArray();

        return new RequestTrace
        {
            RequestId = input.Request.RequestId,
            SessionId = input.Context.SessionId,
            Composition = input.Request.Options.CompositionId
                ?? TryGetMetadataString(input.Plan?.Metadata, "compositionId"),
            SelectedExperts = selectedExperts,
            RouterDecision = CreateRouterDecision(input.Plan),
            LatencyMs = Math.Max(0, (input.CompletedAt - input.StartedAt).TotalMilliseconds),
            TokenUsage = EstimateTokenUsage(input.Request, input.ExpertResults, input.VerifiedResult),
            MemoryUsage = EstimateMemoryUsage(input.ExpertResults, input.Plan),
            ExpertOutputs = input.ExpertResults.Select(ToExpertOutputTrace).ToArray(),
            JudgeScore = input.VerifiedResult?.Score ?? 0,
            FinalAnswer = input.VerifiedResult?.FinalAnswer
                ?? input.AggregatedResult?.Output
                ?? string.Empty,
            FallbackUsed = input.RecoveryDecision?.ShouldRecover == true,
            Error = errors.Length > 0 || input.VerifiedResult?.NeedsRetry == true,
            Errors = errors,
            Stages = input.Context.ExecutionHistory.Select(ToStageTrace).ToArray(),
            Metadata = new Dictionary<string, object>
            {
                ["inputType"] = input.Request.TaskType ?? DetectInputType(input.Request),
                ["aggregationStrategy"] = input.AggregatedResult?.Strategy ?? string.Empty,
                ["selectedExpertId"] = input.AggregatedResult?.SelectedExpertId ?? string.Empty,
                ["recoveryAction"] = input.RecoveryDecision?.Action ?? string.Empty,
                ["needsRetry"] = input.VerifiedResult?.NeedsRetry ?? false
            }
        };
    }

    private static string CreateRouterDecision(ExecutionPlan? plan)
    {
        if (plan is null)
        {
            return string.Empty;
        }

        var expertPath = string.Join(" -> ", plan.Steps.OrderBy(step => step.Order).Select(step => step.ExpertId));
        return $"{(plan.RunInParallel ? "parallel" : "serial")}:{expertPath}";
    }

    private static ExpertOutputTrace ToExpertOutputTrace(ExpertResult result)
    {
        return new ExpertOutputTrace
        {
            ExpertId = result.ExpertId,
            Output = result.Output,
            Confidence = result.Confidence,
            Succeeded = result.Succeeded,
            LatencyMs = result.LatencyMs > 0 ? result.LatencyMs : result.Duration.TotalMilliseconds,
            Warnings = result.Warnings,
            Error = result.Error
        };
    }

    private static StageTrace ToStageTrace(ExecutionHistoryEntry entry)
    {
        return new StageTrace
        {
            Stage = entry.Step,
            Actor = entry.Actor,
            Succeeded = entry.Succeeded,
            DurationMs = entry.Duration.TotalMilliseconds,
            InputSummary = entry.InputSummary,
            OutputSummary = entry.OutputSummary
        };
    }

    private static TokenUsage EstimateTokenUsage(
        CloudAIRequest request,
        IReadOnlyList<ExpertResult> results,
        VerifiedResult? verified)
    {
        return new TokenUsage
        {
            InputTokens = EstimateTokens(request.Input),
            OutputTokens = results.Sum(result => EstimateTokens(result.Output))
                + EstimateTokens(verified?.FinalAnswer ?? string.Empty)
        };
    }

    private static MemoryUsage EstimateMemoryUsage(
        IReadOnlyList<ExpertResult> results,
        ExecutionPlan? plan)
    {
        var memoryFromResults = results
            .Select(result => result.Metadata.TryGetValue("requiredMemoryMb", out var value) && value is long memory ? memory : 0)
            .Sum();

        return new MemoryUsage
        {
            RequiredMemoryMb = memoryFromResults,
            EstimatedUsedMemoryMb = memoryFromResults,
            PeakMemoryMb = memoryFromResults
        };
    }

    private static long EstimateTokens(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return 0;
        }

        return Math.Max(1, value.Length / 4);
    }

    private static string DetectInputType(CloudAIRequest request)
    {
        var input = request.Input.ToLowerInvariant();

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

    private static bool ContainsAny(string input, params string[] needles)
    {
        return needles.Any(needle => input.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }

    private static string? TryGetMetadataString(IReadOnlyDictionary<string, object>? metadata, string key)
    {
        return metadata is not null && metadata.TryGetValue(key, out var value)
            ? value?.ToString()
            : null;
    }
}
