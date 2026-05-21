using System.Diagnostics;

namespace LocalAI.CloudInterface;

public sealed class DefaultExpertRuntimeAdapter : IExpertRuntimeAdapter
{
    public bool CanHandle(ExpertDefinition definition)
    {
        return true;
    }

    public IExpert CreateExpert(ExpertDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);

        return definition.Profile.Id switch
        {
            "rule-based-response" => new RuleBasedResponseExpert(),
            _ => new RegisteredExpert(definition.Profile)
        };
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

    public Task<ExpertHealth> CheckHealthAsync(ExpertDefinition definition, string state)
    {
        ArgumentNullException.ThrowIfNull(definition);

        var stopwatch = Stopwatch.StartNew();
        var isAttached = state is ExpertLifecycleState.Attached or ExpertLifecycleState.Loaded or ExpertLifecycleState.Unloaded;
        var isLoaded = state == ExpertLifecycleState.Loaded;
        var status = isAttached
            ? ExpertHealthStatus.Healthy
            : ExpertHealthStatus.Unavailable;

        stopwatch.Stop();
        return Task.FromResult(new ExpertHealth
        {
            ExpertId = definition.Profile.Id,
            Status = status,
            State = state,
            IsAttached = isAttached,
            IsLoaded = isLoaded,
            LatencyMs = stopwatch.Elapsed.TotalMilliseconds,
            Message = isAttached ? "Expert definition is attached." : "Expert definition is not attached.",
            Metadata = new Dictionary<string, object>
            {
                ["provider"] = definition.Profile.Provider,
                ["modelType"] = definition.Profile.ModelType,
                ["preload"] = definition.Preload,
                ["keepAlive"] = definition.KeepAlive
            }
        });
    }
}
