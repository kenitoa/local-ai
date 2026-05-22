namespace LocalAI.CloudInterface;

public static class FailureType
{
    public const string ExpertTimeout = "expert-timeout";
    public const string ModelUnavailable = "model-unavailable";
    public const string InvalidJson = "invalid-json";
    public const string LowConfidence = "low-confidence";
    public const string ContradictoryAnswers = "contradictory-answers";
    public const string OutOfMemory = "out-of-memory";
    public const string RateLimit = "rate-limit";
    public const string Unknown = "unknown";
}
