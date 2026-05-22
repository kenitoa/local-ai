namespace LocalAI.CloudInterface;

public sealed class EmbeddingExpert : ExpertAdapterBase
{
    public EmbeddingExpert(Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(CreateProfile(), invokeAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "embedding",
            Provider = "HuggingFace",
            ModelType = "embedding",
            Capabilities = ["embedding", "search", "reranker"],
            Priority = 15,
            CostScore = 0.9,
            LatencyScore = 0.8,
            QualityScore = 0.7,
            RequiredMemoryMb = 1024,
            SupportsStreaming = false,
            SupportsJsonOutput = true
        };
    }
}
