namespace LocalAI.CloudInterface;

public sealed class DotNetCustomExpert : ExpertAdapterBase
{
    public DotNetCustomExpert(Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(CreateProfile(), invokeAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "dotnet-custom",
            Provider = "CustomDotNet",
            ModelType = "custom",
            Capabilities = ["planning", "code", "rules"],
            Priority = 30,
            CostScore = 1.0,
            LatencyScore = 0.85,
            QualityScore = 0.7,
            RequiredMemoryMb = 256,
            SupportsStreaming = false,
            SupportsJsonOutput = true
        };
    }
}
