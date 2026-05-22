namespace LocalAI.CloudInterface;

public interface IRouter
{
    Task<ExecutionPlan> CreatePlanAsync(
        CloudAIRequest request,
        RuntimeContext context,
        IReadOnlyList<IExpert> experts);
}
