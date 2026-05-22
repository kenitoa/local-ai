using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class ParallelExecutionEngine : IExecutionEngine
{
    private readonly IExpertRegistry expertRegistry;
    private readonly IExpertRuntimeLimitProvider limitProvider;
    private readonly IExpertPermissionStore permissionStore;
    private readonly IExpertSecurityFilter securityFilter;
    private readonly ConcurrentDictionary<string, ExpertExecutionGate> gates = new(StringComparer.OrdinalIgnoreCase);

    public ParallelExecutionEngine(
        IExpertRegistry expertRegistry,
        IExpertRuntimeLimitProvider? limitProvider = null,
        IExpertPermissionStore? permissionStore = null,
        IExpertSecurityFilter? securityFilter = null)
    {
        this.expertRegistry = expertRegistry;
        this.limitProvider = limitProvider ?? new DefaultExpertRuntimeLimitProvider();
        this.permissionStore = permissionStore ?? new InMemoryExpertPermissionStore();
        this.securityFilter = securityFilter ?? new DefaultExpertSecurityFilter();
    }

    public async Task<IReadOnlyList<ExpertResult>> ExecuteAsync(
        ExecutionPlan plan,
        RuntimeContext context)
    {
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(context);

        var experts = await expertRegistry.GetAllAsync().ConfigureAwait(false);
        var expertsById = experts.ToDictionary(expert => expert.Id, StringComparer.OrdinalIgnoreCase);
        var orderedSteps = plan.Steps.OrderBy(step => step.Order).ToList();

        var results = new List<ExpertResult>();
        var completedExpertIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var remainingSteps = new List<ExecutionStep>(orderedSteps);

        while (remainingSteps.Count > 0)
        {
            var readySteps = remainingSteps
                .Where(step => step.DependsOnExpertIds.All(completedExpertIds.Contains))
                .OrderBy(step => step.Order)
                .ToArray();

            if (readySteps.Length == 0)
            {
                results.Add(CreatePlannerFailure("No executable step was found. Check step dependencies."));
                break;
            }

            var batch = SelectBatch(plan, readySteps);
            var batchResults = await Task.WhenAll(batch.Select(step => ExecuteStepAsync(step, context, expertsById)))
                .ConfigureAwait(false);

            foreach (var result in batchResults)
            {
                results.Add(result);
                completedExpertIds.Add(result.ExpertId);
            }

            foreach (var step in batch)
            {
                remainingSteps.Remove(step);
            }
        }

        lock (context)
        {
            context.ExecutionHistory.Add(new ExecutionHistoryEntry
            {
                Step = "ExecutionEngine.Execute",
                Actor = nameof(ParallelExecutionEngine),
                OutputSummary = string.Join(" -> ", results.Select(result => result.ExpertId)),
                Succeeded = results.Count > 0 && results.All(result => result.Succeeded),
                Metadata = new Dictionary<string, object>
                {
                    ["planId"] = plan.PlanId,
                    ["resultCount"] = results.Count,
                    ["runInParallel"] = plan.RunInParallel
                }
            });
        }

        return results;
    }

    private static IReadOnlyList<ExecutionStep> SelectBatch(ExecutionPlan plan, IReadOnlyList<ExecutionStep> readySteps)
    {
        if (!plan.RunInParallel)
        {
            return [readySteps[0]];
        }

        var parallelSteps = readySteps.Where(step => step.CanRunInParallel).ToArray();
        return parallelSteps.Length > 0 ? parallelSteps : [readySteps[0]];
    }

    private async Task<ExpertResult> ExecuteStepAsync(
        ExecutionStep step,
        RuntimeContext context,
        IReadOnlyDictionary<string, IExpert> expertsById)
    {
        if (!expertsById.TryGetValue(step.ExpertId, out var expert))
        {
            return CreateMissingExpertResult(step.ExpertId);
        }

        var limit = limitProvider.GetLimit(expert);
        if (limit.MaxMemoryMb > 0 && expert.Profile.RequiredMemoryMb > limit.MaxMemoryMb)
        {
            return CreateLimitFailure(expert.Id, $"Expert requires {expert.Profile.RequiredMemoryMb} MB, over limit {limit.MaxMemoryMb} MB.");
        }

        var gate = gates.GetOrAdd(expert.Id, _ => new ExpertExecutionGate(limit));
        var attempts = Math.Max(0, limit.MaxRetries) + 1;
        ExpertResult? lastResult = null;

        for (var attempt = 1; attempt <= attempts; attempt++)
        {
            if (gate.IsCircuitOpen())
            {
                return CreateLimitFailure(expert.Id, "Circuit breaker is open for this expert.");
            }

            var acquired = await gate.Semaphore.WaitAsync(limit.Timeout).ConfigureAwait(false);
            if (!acquired)
            {
                lastResult = CreateLimitFailure(expert.Id, "Concurrency wait timed out.");
                gate.RecordFailure();
                continue;
            }

            try
            {
                await gate.WaitForRateLimitAsync().ConfigureAwait(false);

                var permissions = await permissionStore.GetAsync(expert.Id).ConfigureAwait(false);
                var request = CreateExpertRequest(step, context);
                var securityResult = await securityFilter.FilterRequestAsync(expert, request, permissions).ConfigureAwait(false);
                if (!securityResult.Allowed)
                {
                    lastResult = CreateSecurityFailure(expert.Id, securityResult.Violations);
                    gate.RecordFailure();
                    continue;
                }

                var result = await expert.InvokeAsync(securityResult.Request).WaitAsync(limit.Timeout).ConfigureAwait(false);
                var filteredResult = await securityFilter.FilterResultAsync(expert, result, permissions).ConfigureAwait(false);
                lastResult = NormalizeResult(expert.Id, filteredResult);

                if (lastResult.Succeeded)
                {
                    gate.RecordSuccess();
                    return lastResult;
                }

                gate.RecordFailure();
            }
            catch (TimeoutException)
            {
                lastResult = CreateLimitFailure(expert.Id, $"Expert execution timed out after {limit.Timeout}.");
                gate.RecordFailure();
            }
            catch (Exception ex)
            {
                lastResult = CreateLimitFailure(expert.Id, ex.Message);
                gate.RecordFailure();
            }
            finally
            {
                gate.Semaphore.Release();
            }
        }

        return lastResult ?? CreateLimitFailure(expert.Id, "Expert execution failed without a result.");
    }

    private static ExpertRequest CreateExpertRequest(ExecutionStep step, RuntimeContext context)
    {
        var input = TryGetString(context.WorkingMemory, "input")
            ?? context.Conversation.LastOrDefault(message => message.Role.Equals("user", StringComparison.OrdinalIgnoreCase))?.Content
            ?? context.TaskState.Goal
            ?? string.Empty;

        return new ExpertRequest
        {
            RequestId = TryGetString(context.WorkingMemory, "requestId") ?? Guid.NewGuid().ToString("N"),
            UserId = TryGetString(context.UserMemory, "userId") ?? "anonymous",
            Input = input,
            TaskType = TryGetString(context.WorkingMemory, "taskType"),
            ExpectedOutputFormat = TryGetString(step.Metadata, "expectedOutputFormat"),
            Context = new Dictionary<string, object>
            {
                ["executionStep"] = step.Role,
                ["executionReason"] = step.Reason
            },
            SharedContext = context,
            Options = context.WorkingMemory.TryGetValue("runtimeOptions", out var options) && options is RuntimeOptions runtimeOptions
                ? runtimeOptions
                : new RuntimeOptions()
        };
    }

    private static ExpertResult NormalizeResult(string expertId, ExpertResult result)
    {
        if (!string.IsNullOrWhiteSpace(result.ExpertId))
        {
            return result;
        }

        return new ExpertResult
        {
            ExpertId = expertId,
            Output = result.Output,
            Confidence = result.Confidence,
            Succeeded = result.Succeeded,
            IsJsonOutput = result.IsJsonOutput,
            Duration = result.Duration,
            LatencyMs = result.LatencyMs,
            Error = result.Error,
            Warnings = result.Warnings,
            Metadata = result.Metadata
        };
    }

    private static ExpertResult CreateMissingExpertResult(string expertId)
    {
        return CreateLimitFailure(expertId, "Expert is not registered.");
    }

    private static ExpertResult CreateSecurityFailure(
        string expertId,
        IReadOnlyList<SecurityViolation> violations)
    {
        return new ExpertResult
        {
            ExpertId = expertId,
            Succeeded = false,
            Confidence = 0,
            Error = "Security policy blocked expert execution.",
            Warnings = violations.Select(violation => $"{violation.Code}: {violation.Message}").ToArray(),
            Metadata = new Dictionary<string, object>
            {
                ["securityViolations"] = violations
            }
        };
    }

    private static ExpertResult CreatePlannerFailure(string error)
    {
        return CreateLimitFailure("execution-engine", error);
    }

    private static ExpertResult CreateLimitFailure(string expertId, string error)
    {
        return new ExpertResult
        {
            ExpertId = expertId,
            Succeeded = false,
            Confidence = 0,
            Error = error
        };
    }

    private static string? TryGetString(IReadOnlyDictionary<string, object> values, string key)
    {
        return values.TryGetValue(key, out var value) ? value?.ToString() : null;
    }

    private sealed class ExpertExecutionGate
    {
        private readonly object sync = new();
        private readonly TimeSpan minDelayBetweenRequests;
        private readonly int circuitBreakerFailureThreshold;
        private readonly TimeSpan circuitBreakerBreakDuration;
        private DateTimeOffset nextAllowedAt;
        private DateTimeOffset circuitOpenUntil;
        private int consecutiveFailures;

        public ExpertExecutionGate(ExpertRuntimeLimit limit)
        {
            Semaphore = new SemaphoreSlim(Math.Max(1, limit.MaxConcurrentRequests), Math.Max(1, limit.MaxConcurrentRequests));
            minDelayBetweenRequests = limit.MinDelayBetweenRequests;
            circuitBreakerFailureThreshold = Math.Max(1, limit.CircuitBreakerFailureThreshold);
            circuitBreakerBreakDuration = limit.CircuitBreakerBreakDuration;
        }

        public SemaphoreSlim Semaphore { get; }

        public bool IsCircuitOpen()
        {
            lock (sync)
            {
                return circuitOpenUntil > DateTimeOffset.UtcNow;
            }
        }

        public async Task WaitForRateLimitAsync()
        {
            TimeSpan delay;
            lock (sync)
            {
                var now = DateTimeOffset.UtcNow;
                delay = nextAllowedAt > now ? nextAllowedAt - now : TimeSpan.Zero;
                nextAllowedAt = (delay == TimeSpan.Zero ? now : nextAllowedAt) + minDelayBetweenRequests;
            }

            if (delay > TimeSpan.Zero)
            {
                await Task.Delay(delay).ConfigureAwait(false);
            }
        }

        public void RecordSuccess()
        {
            lock (sync)
            {
                consecutiveFailures = 0;
                circuitOpenUntil = DateTimeOffset.MinValue;
            }
        }

        public void RecordFailure()
        {
            lock (sync)
            {
                consecutiveFailures++;
                if (consecutiveFailures >= circuitBreakerFailureThreshold)
                {
                    circuitOpenUntil = DateTimeOffset.UtcNow + circuitBreakerBreakDuration;
                }
            }
        }
    }
}
