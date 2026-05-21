namespace LocalAI.CloudInterface;

public sealed class OllamaExpert : ExpertAdapterBase
{
    public OllamaExpert(Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(CreateProfile(), invokeAsync)
    {
    }

    private static ExpertProfile CreateProfile()
    {
        return new ExpertProfile
        {
            Id = "ollama",
            Provider = "Ollama",
            ModelType = "llm",
            Capabilities = ["korean", "code", "reasoning", "summarization"],
            Priority = 10,
            CostScore = 1.0,
            LatencyScore = 0.6,
            QualityScore = 0.75,
            RequiredMemoryMb = 4096,
            SupportsStreaming = true,
            SupportsJsonOutput = true
        };
    }
}
