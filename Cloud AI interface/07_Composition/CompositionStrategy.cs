namespace LocalAI.CloudInterface;

public static class CompositionStrategy
{
    public const string Single = "single";
    public const string Pipeline = "pipeline";
    public const string ParallelVote = "parallel-vote";
    public const string ParallelJudge = "parallel-judge";
    public const string FallbackChain = "fallback-chain";
}
