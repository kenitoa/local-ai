namespace LocalAI.CloudInterface;

public sealed class MLNetExpert : ExpertAdapterBase
{
    public MLNetExpert(Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(CreateProfile(), invokeAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "mlnet",
            Provider = "MLNet",
            ModelType = "classifier",
            Capabilities = ["classification", "scoring"],
            Priority = 20,
            CostScore = 1.0,
            LatencyScore = 0.9,
            QualityScore = 0.65,
            RequiredMemoryMb = 512,
            SupportsStreaming = false,
            SupportsJsonOutput = true
        };
    }
}
