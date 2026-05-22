namespace LocalAI.CloudInterface;

public abstract class ExpertAdapterBase : IExpert
{
    private readonly Func<ExpertRequest, Task<ExpertResult>>? invokeAsync;

    protected ExpertAdapterBase(ExpertProfile profile, Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
    {
        Profile = profile;
        this.invokeAsync = invokeAsync;
    }

    public string Id => Profile.Id;
    public ExpertProfile Profile { get; }

    public async Task<ExpertResult> InvokeAsync(ExpertRequest request)
    {
        var startedAt = DateTimeOffset.UtcNow;

        if (invokeAsync is null)
        {
            var notConfiguredResult = CreateNotConfiguredResult(startedAt);
            RecordSharedContext(request, notConfiguredResult);
            return notConfiguredResult;
        }

        try
        {
            var result = await invokeAsync(request).ConfigureAwait(false);
            var normalizedResult = EnsureExpertIdAndDuration(result, startedAt);
            RecordSharedContext(request, normalizedResult);
            return normalizedResult;
        }
        catch (Exception ex)
        {
            var failedResult = new ExpertResult
            {
                ExpertId = Id,
                Succeeded = false,
                Confidence = 0,
                Error = ex.Message,
                Duration = DateTimeOffset.UtcNow - startedAt
            };

            RecordSharedContext(request, failedResult);
            return failedResult;
        }
    }

    private ExpertResult CreateNotConfiguredResult(DateTimeOffset startedAt)
    {
        return new ExpertResult
        {
            ExpertId = Id,
            Succeeded = false,
            Confidence = 0,
            Error = $"{GetType().Name} is not configured with an execution delegate.",
            Duration = DateTimeOffset.UtcNow - startedAt
        };
    }

    private ExpertResult EnsureExpertIdAndDuration(ExpertResult result, DateTimeOffset startedAt)
    {
        return new ExpertResult
        {
            ExpertId = string.IsNullOrWhiteSpace(result.ExpertId) ? Id : result.ExpertId,
            Output = result.Output,
            Confidence = result.Confidence,
            Succeeded = result.Succeeded,
            IsJsonOutput = result.IsJsonOutput,
            Duration = result.Duration == TimeSpan.Zero ? DateTimeOffset.UtcNow - startedAt : result.Duration,
            LatencyMs = result.LatencyMs > 0
                ? result.LatencyMs
                : (result.Duration == TimeSpan.Zero ? DateTimeOffset.UtcNow - startedAt : result.Duration).TotalMilliseconds,
            Error = result.Error,
            Warnings = result.Warnings,
            Metadata = result.Metadata
        };
    }

    private void RecordSharedContext(ExpertRequest request, ExpertResult result)
    {
        var context = request.SharedContext;
        lock (context)
        {
            context.PreviousResults.Add(result);
            context.ExecutionHistory.Add(new ExecutionHistoryEntry
            {
                Step = "Expert.Invoke",
                Actor = Id,
                InputSummary = Summarize(request.Input),
                OutputSummary = Summarize(result.Output),
                Succeeded = result.Succeeded,
                Duration = result.Duration,
                Metadata = new Dictionary<string, object>
                {
                    ["taskType"] = request.TaskType ?? string.Empty,
                    ["confidence"] = result.Confidence
                }
            });
        }
    }

    private static string Summarize(string value)
    {
        const int maxLength = 240;

        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        var trimmed = value.Trim();
        return trimmed.Length <= maxLength ? trimmed : trimmed[..maxLength];
    }
}
