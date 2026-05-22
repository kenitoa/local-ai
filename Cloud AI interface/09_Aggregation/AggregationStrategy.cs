namespace LocalAI.CloudInterface;

public static class AggregationStrategy
{
    public const string BestConfidence = "best-confidence";
    public const string WeightedScore = "weighted-score";
    public const string MajorityVote = "majority-vote";
    public const string LlmSummarization = "llm-summarization";
    public const string JudgeSelection = "judge-selection";
}
