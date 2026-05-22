namespace LocalAI.CloudInterface;

public sealed class SemanticKernelOllamaRuntimeAdapter : IExpertRuntimeAdapter
{
    public bool CanHandle(ExpertDefinition definition)
    {
        return definition.Profile.Provider.Equals("ollama", StringComparison.OrdinalIgnoreCase);
    }

    public IExpert CreateExpert(ExpertDefinition definition)
    {
        return new SemanticKernelOllamaExpert(definition);
    }

    public Task LoadAsync(ExpertDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);
        return Task.CompletedTask;
    }

    public Task UnloadAsync(ExpertDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);
        return Task.CompletedTask;
    }

    public async Task<ExpertHealth> CheckHealthAsync(ExpertDefinition definition, string state)
    {
        ArgumentNullException.ThrowIfNull(definition);

        var expert = new SemanticKernelOllamaExpert(definition);
        var health = await expert.CheckHealthAsync().ConfigureAwait(false);

        return new ExpertHealth
        {
            ExpertId = definition.Profile.Id,
            Status = health.ModelInstalled ? ExpertHealthStatus.Healthy : ExpertHealthStatus.Degraded,
            State = state,
            IsAttached = true,
            IsLoaded = state == ExpertLifecycleState.Loaded,
            LatencyMs = health.LatencyMs,
            Message = health.Error ?? (health.ModelInstalled ? "Ollama model is available." : "Ollama model is not installed or server is unavailable."),
            Metadata = new Dictionary<string, object>
            {
                ["endpoint"] = health.Endpoint,
                ["modelId"] = health.ModelId,
                ["reachable"] = health.IsReachable,
                ["installedModels"] = health.InstalledModels
            }
        };
    }
}
