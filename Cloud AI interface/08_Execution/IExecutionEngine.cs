namespace LocalAI.CloudInterface;

public interface IExecutionEngine
{
    Task<IReadOnlyList<ExpertResult>> ExecuteAsync(
        ExecutionPlan plan,
        RuntimeContext context);
}
