namespace LocalAI.CloudInterface;

public sealed class DefaultExpertSecurityFilter : IExpertSecurityFilter
{
    public Task<SecurityFilterResult> FilterRequestAsync(
        IExpert expert,
        ExpertRequest request,
        ExpertPermissions permissions)
    {
        ArgumentNullException.ThrowIfNull(expert);
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(permissions);

        var violations = new List<SecurityViolation>();
        if (ContainsPromptInjectionSignal(request.Input))
        {
            violations.Add(new SecurityViolation
            {
                Code = "prompt-injection",
                Message = "Input contains prompt-injection-like instructions.",
                Severity = "error"
            });
        }

        if (!permissions.CanCallExternalApi && RequestsExternalApi(request))
        {
            violations.Add(new SecurityViolation
            {
                Code = "external-api-denied",
                Message = "Expert is not allowed to call external APIs.",
                Severity = "error"
            });
        }

        if (!permissions.CanUseTools && request.Context.ContainsKey("tool"))
        {
            violations.Add(new SecurityViolation
            {
                Code = "tool-access-denied",
                Message = "Expert is not allowed to call tools.",
                Severity = "error"
            });
        }

        var filteredRequest = CreateFilteredRequest(request, permissions);
        return Task.FromResult(new SecurityFilterResult
        {
            Allowed = violations.All(violation => violation.Severity != "error"),
            Request = filteredRequest,
            Violations = violations
        });
    }

    public Task<ExpertResult> FilterResultAsync(
        IExpert expert,
        ExpertResult result,
        ExpertPermissions permissions)
    {
        ArgumentNullException.ThrowIfNull(expert);
        ArgumentNullException.ThrowIfNull(result);
        ArgumentNullException.ThrowIfNull(permissions);

        var warnings = result.Warnings.ToList();
        if (!permissions.CanReceiveSensitiveData)
        {
            warnings.Add("sensitive data masked");
        }

        return Task.FromResult(new ExpertResult
        {
            ExpertId = result.ExpertId,
            Output = permissions.CanReceiveSensitiveData ? result.Output : SensitiveDataMasker.Mask(result.Output),
            Confidence = result.Confidence,
            Succeeded = result.Succeeded,
            IsJsonOutput = result.IsJsonOutput,
            Duration = result.Duration,
            LatencyMs = result.LatencyMs,
            Error = result.Error,
            Warnings = warnings.Distinct().ToArray(),
            Metadata = permissions.CanReceiveSensitiveData ? result.Metadata : SensitiveDataMasker.MaskMetadata(result.Metadata)
        });
    }

    private static ExpertRequest CreateFilteredRequest(ExpertRequest request, ExpertPermissions permissions)
    {
        var context = request.Context
            .Where(item => IsContextAllowed(item.Key, permissions))
            .ToDictionary(item => item.Key, item => item.Value, StringComparer.OrdinalIgnoreCase);

        return new ExpertRequest
        {
            RequestId = request.RequestId,
            UserId = request.UserId,
            Input = permissions.CanReceiveSensitiveData ? request.Input : SensitiveDataMasker.Mask(request.Input),
            TaskType = request.TaskType,
            ExpectedOutputFormat = request.ExpectedOutputFormat,
            Context = context,
            SharedContext = request.SharedContext,
            Options = request.Options
        };
    }

    private static bool IsContextAllowed(string key, ExpertPermissions permissions)
    {
        if (key.Contains("file", StringComparison.OrdinalIgnoreCase) && !permissions.CanReadFiles)
        {
            return false;
        }

        if (key.Contains("internet", StringComparison.OrdinalIgnoreCase) && !permissions.CanAccessInternet)
        {
            return false;
        }

        if (key.Contains("external", StringComparison.OrdinalIgnoreCase) && !permissions.CanCallExternalApi)
        {
            return false;
        }

        if (key.Contains("tool", StringComparison.OrdinalIgnoreCase) && !permissions.CanUseTools)
        {
            return false;
        }

        return true;
    }

    private static bool ContainsPromptInjectionSignal(string input)
    {
        return ContainsAny(input,
            "ignore previous instructions",
            "ignore all previous",
            "system prompt",
            "developer message",
            "reveal hidden",
            "jailbreak",
            "프롬프트 무시",
            "이전 지시 무시");
    }

    private static bool RequestsExternalApi(ExpertRequest request)
    {
        return request.Context.Keys.Any(key => key.Contains("external", StringComparison.OrdinalIgnoreCase))
            || ContainsAny(request.Input, "call external api", "send to api", "internet search", "외부 api");
    }

    private static bool ContainsAny(string input, params string[] needles)
    {
        return needles.Any(needle => input.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }
}
