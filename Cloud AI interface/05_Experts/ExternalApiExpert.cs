namespace LocalAI.CloudInterface;

public sealed class ExternalApiExpert : ExpertAdapterBase
{
    public ExternalApiExpert(Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(CreateProfile(), invokeAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "external-api",
            Provider = "OpenAI",
            ModelType = "llm",
            Capabilities = ["reasoning", "summarization", "search", "planning"],
            Priority = 40,
            CostScore = 0.35,
            LatencyScore = 0.55,
            QualityScore = 0.9,
            RequiredMemoryMb = 0,
            SupportsStreaming = true,
            SupportsJsonOutput = true
        };
    }
}
