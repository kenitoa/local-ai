namespace LocalAI.CloudInterface;

public interface ISelfOptimizer
{
    Task RecordAsync(RequestTrace trace, UserFeedback? feedback = null);
    Task<OptimizationRecommendation> RecommendAsync(CloudAIRequest request);
}
