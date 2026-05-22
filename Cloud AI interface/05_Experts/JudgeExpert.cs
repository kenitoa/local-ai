namespace LocalAI.CloudInterface;

public sealed class JudgeExpert : ExpertAdapterBase
{
    public JudgeExpert(Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(CreateProfile(), invokeAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "judge",
            Provider = "CustomDotNet",
            ModelType = "judge",
            Capabilities = ["judge", "verification", "classification"],
            Priority = 5,
            CostScore = 1.0,
            LatencyScore = 0.75,
            QualityScore = 0.8,
            RequiredMemoryMb = 512,
            SupportsStreaming = false,
            SupportsJsonOutput = true
        };
    }
}
