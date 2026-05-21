using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryCompositionProfileRegistry : ICompositionProfileRegistry
{
    private readonly ConcurrentDictionary<string, CompositionProfile> profiles = new(StringComparer.OrdinalIgnoreCase);

    public Task RegisterAsync(CompositionProfile profile)
    {
        ArgumentNullException.ThrowIfNull(profile);

        if (string.IsNullOrWhiteSpace(profile.CompositionId))
        {
            throw new ArgumentException("Composition id is required.", nameof(profile));
        }

        profiles[profile.CompositionId] = profile;
        return Task.CompletedTask;
    }

    public Task UnregisterAsync(string compositionId)
    {
        if (!string.IsNullOrWhiteSpace(compositionId))
        {
            profiles.TryRemove(compositionId, out _);
        }

        return Task.CompletedTask;
    }

    public Task<CompositionProfile?> GetAsync(string compositionId)
    {
        if (string.IsNullOrWhiteSpace(compositionId))
        {
            return Task.FromResult<CompositionProfile?>(null);
        }

        profiles.TryGetValue(compositionId, out var profile);
        return Task.FromResult(profile);
    }

    public Task<IReadOnlyList<CompositionProfile>> GetAllAsync()
    {
        var ordered = profiles.Values
            .OrderBy(profile => profile.CompositionId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return Task.FromResult<IReadOnlyList<CompositionProfile>>(ordered);
    }

    public Task<IReadOnlyList<CompositionProfile>> FindByExpertAsync(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId))
        {
            return Task.FromResult<IReadOnlyList<CompositionProfile>>(Array.Empty<CompositionProfile>());
        }

        var matches = profiles.Values
            .Where(profile => profile.Experts.Concat(profile.Fallback).Any(id =>
                string.Equals(id, expertId, StringComparison.OrdinalIgnoreCase)))
            .OrderBy(profile => profile.CompositionId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return Task.FromResult<IReadOnlyList<CompositionProfile>>(matches);
    }

    public Task<IReadOnlyList<CompositionProfile>> FindByStrategyAsync(string strategy)
    {
        if (string.IsNullOrWhiteSpace(strategy))
        {
            return Task.FromResult<IReadOnlyList<CompositionProfile>>(Array.Empty<CompositionProfile>());
        }

        var matches = profiles.Values
            .Where(profile => string.Equals(profile.Strategy, strategy, StringComparison.OrdinalIgnoreCase))
            .OrderBy(profile => profile.CompositionId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return Task.FromResult<IReadOnlyList<CompositionProfile>>(matches);
    }
}
