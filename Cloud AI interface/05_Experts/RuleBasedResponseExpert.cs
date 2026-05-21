namespace LocalAI.CloudInterface;

public sealed class RuleBasedResponseExpert : ExpertAdapterBase
{
    public RuleBasedResponseExpert()
        : base(CreateProfile(), InvokeRuleBasedAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "rule-based-response",
            Provider = "rule-based",
            ModelType = "fallback",
            Capabilities = ["fallback", "safe-response"],
            Priority = 1000,
            CostScore = 1.0,
            LatencyScore = 1.0,
            QualityScore = 0.35,
            SupportsJsonOutput = true
        };
    }

    private static Task<ExpertResult> InvokeRuleBasedAsync(ExpertRequest request)
    {
        var output = string.IsNullOrWhiteSpace(request.Input)
            ? "The request could not be completed by the available experts."
            : $"The request could not be completed by the available experts. Input summary: {request.Input.Trim()}";

        return Task.FromResult(new ExpertResult
        {
            ExpertId = "rule-based-response",
            Output = output,
            Confidence = 0.35,
            Succeeded = true,
            IsJsonOutput = false,
            Warnings = ["rule-based fallback response"]
        });
    }
}
