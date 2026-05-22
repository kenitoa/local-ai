namespace LocalAI.CloudInterface;

public interface IExpertLifecycleManager
{
    Task AttachAsync(ExpertDefinition definition);
    Task DetachAsync(string expertId);
    Task LoadAsync(string expertId);
    Task UnloadAsync(string expertId);
    Task<ExpertHealth> CheckHealthAsync(string expertId);
}
