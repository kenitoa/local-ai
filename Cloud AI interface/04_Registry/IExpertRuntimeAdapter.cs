namespace LocalAI.CloudInterface;

public interface IExpertRuntimeAdapter
{
    bool CanHandle(ExpertDefinition definition);
    IExpert CreateExpert(ExpertDefinition definition);
    Task LoadAsync(ExpertDefinition definition);
    Task UnloadAsync(ExpertDefinition definition);
    Task<ExpertHealth> CheckHealthAsync(ExpertDefinition definition, string state);
}
