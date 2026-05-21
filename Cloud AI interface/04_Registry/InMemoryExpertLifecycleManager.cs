using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryExpertLifecycleManager : IExpertLifecycleManager
{
    private readonly IExpertRegistry registry;
    private readonly IReadOnlyList<IExpertRuntimeAdapter> adapters;
    private readonly ConcurrentDictionary<string, ExpertDefinition> definitions = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> states = new(StringComparer.OrdinalIgnoreCase);

    public InMemoryExpertLifecycleManager(
        IExpertRegistry registry,
        IReadOnlyList<IExpertRuntimeAdapter>? adapters = null)
    {
        this.registry = registry;
        this.adapters = adapters is { Count: > 0 }
            ? adapters
            : [new DefaultExpertRuntimeAdapter()];
    }

    public async Task AttachAsync(ExpertDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);

        if (string.IsNullOrWhiteSpace(definition.Profile.Id))
        {
            throw new ArgumentException("Expert id is required.", nameof(definition));
        }

        var adapter = ResolveAdapter(definition);
        var expert = adapter.CreateExpert(definition);

        definitions[definition.Profile.Id] = definition;
        states[definition.Profile.Id] = ExpertLifecycleState.Attached;
        await registry.RegisterAsync(expert).ConfigureAwait(false);

        if (definition.Preload)
        {
            await LoadAsync(definition.Profile.Id).ConfigureAwait(false);
        }
    }

    public async Task DetachAsync(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId))
        {
            return;
        }

        if (states.TryGetValue(expertId, out var state) && state == ExpertLifecycleState.Loaded)
        {
            await UnloadAsync(expertId).ConfigureAwait(false);
        }

        definitions.TryRemove(expertId, out _);
        states[expertId] = ExpertLifecycleState.Detached;
        await registry.UnregisterAsync(expertId).ConfigureAwait(false);
    }

    public async Task LoadAsync(string expertId)
    {
        var definition = GetDefinitionOrThrow(expertId);
        var adapter = ResolveAdapter(definition);

        try
        {
            await adapter.LoadAsync(definition).ConfigureAwait(false);
            states[expertId] = ExpertLifecycleState.Loaded;
        }
        catch
        {
            states[expertId] = ExpertLifecycleState.Failed;
            throw;
        }
    }

    public async Task UnloadAsync(string expertId)
    {
        var definition = GetDefinitionOrThrow(expertId);
        var adapter = ResolveAdapter(definition);

        try
        {
            await adapter.UnloadAsync(definition).ConfigureAwait(false);
            states[expertId] = ExpertLifecycleState.Unloaded;
        }
        catch
        {
            states[expertId] = ExpertLifecycleState.Failed;
            throw;
        }
    }

    public async Task<ExpertHealth> CheckHealthAsync(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId) || !definitions.TryGetValue(expertId, out var definition))
        {
            return new ExpertHealth
            {
                ExpertId = expertId,
                Status = ExpertHealthStatus.Unavailable,
                State = ExpertLifecycleState.Detached,
                IsAttached = false,
                IsLoaded = false,
                Message = "Expert is not attached."
            };
        }

        var state = states.TryGetValue(expertId, out var currentState)
            ? currentState
            : ExpertLifecycleState.Attached;
        var adapter = ResolveAdapter(definition);

        return await adapter.CheckHealthAsync(definition, state).ConfigureAwait(false);
    }

    private ExpertDefinition GetDefinitionOrThrow(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId) || !definitions.TryGetValue(expertId, out var definition))
        {
            throw new InvalidOperationException($"Expert '{expertId}' is not attached.");
        }

        return definition;
    }

    private IExpertRuntimeAdapter ResolveAdapter(ExpertDefinition definition)
    {
        return adapters.FirstOrDefault(adapter => adapter.CanHandle(definition))
            ?? throw new InvalidOperationException($"No runtime adapter can handle expert '{definition.Profile.Id}'.");
    }
}
