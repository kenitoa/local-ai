namespace LocalAI.CloudInterface;

public sealed class LocalModelFileRuntimeAdapter : IExpertRuntimeAdapter
{
    public bool CanHandle(ExpertDefinition definition)
    {
        return definition.Profile.Provider.Equals("mlnet-local", StringComparison.OrdinalIgnoreCase)
            || definition.Profile.Provider.Equals("onnx-local", StringComparison.OrdinalIgnoreCase);
    }

    public IExpert CreateExpert(ExpertDefinition definition)
    {
        return new LocalModelFileExpert(definition);
    }

    public Task LoadAsync(ExpertDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);
        if (string.IsNullOrWhiteSpace(definition.ModelPath) || !File.Exists(definition.ModelPath))
        {
            throw new FileNotFoundException("Local model file was not found.", definition.ModelPath);
        }

        return Task.CompletedTask;
    }

    public Task UnloadAsync(ExpertDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);
        return Task.CompletedTask;
    }

    public Task<ExpertHealth> CheckHealthAsync(ExpertDefinition definition, string state)
    {
        ArgumentNullException.ThrowIfNull(definition);
        var exists = !string.IsNullOrWhiteSpace(definition.ModelPath) && File.Exists(definition.ModelPath);

        return Task.FromResult(new ExpertHealth
        {
            ExpertId = definition.Profile.Id,
            Status = exists ? ExpertHealthStatus.Healthy : ExpertHealthStatus.Unavailable,
            State = state,
            IsAttached = true,
            IsLoaded = state == ExpertLifecycleState.Loaded,
            Message = exists ? "Local model file is mapped." : "Local model file is missing.",
            Metadata = new Dictionary<string, object>
            {
                ["modelPath"] = definition.ModelPath ?? string.Empty,
                ["provider"] = definition.Profile.Provider
            }
        });
    }
}
