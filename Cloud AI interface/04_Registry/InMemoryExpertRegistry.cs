using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryExpertRegistry : IExpertRegistry
{
    private readonly ConcurrentDictionary<string, IExpert> experts = new(StringComparer.OrdinalIgnoreCase);

    public Task RegisterAsync(IExpert expert)
    {
        ArgumentNullException.ThrowIfNull(expert);

        if (string.IsNullOrWhiteSpace(expert.Id))
        {
            throw new ArgumentException("Expert id is required.", nameof(expert));
        }

        experts[expert.Id] = expert;
        return Task.CompletedTask;
    }

    public Task UnregisterAsync(string expertId)
    {
        if (!string.IsNullOrWhiteSpace(expertId))
        {
            experts.TryRemove(expertId, out _);
        }

        return Task.CompletedTask;
    }

    public Task<IExpert?> GetAsync(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId))
        {
            return Task.FromResult<IExpert?>(null);
        }

        experts.TryGetValue(expertId, out var expert);
        return Task.FromResult(expert);
    }

    public Task<IReadOnlyList<IExpert>> FindByCapabilityAsync(string capability)
    {
        if (string.IsNullOrWhiteSpace(capability))
        {
            return Task.FromResult<IReadOnlyList<IExpert>>(Array.Empty<IExpert>());
        }

        var matches = experts.Values
            .Where(expert => expert.Profile.Capabilities.Any(candidate =>
                string.Equals(candidate, capability, StringComparison.OrdinalIgnoreCase)))
            .OrderBy(expert => expert.Profile.Priority)
            .ThenByDescending(expert => expert.Profile.QualityScore)
            .ThenByDescending(expert => expert.Profile.LatencyScore)
            .ThenBy(expert => expert.Id, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return Task.FromResult<IReadOnlyList<IExpert>>(matches);
    }

    public Task<IReadOnlyList<IExpert>> GetAllAsync()
    {
        var ordered = experts.Values
            .OrderBy(expert => expert.Profile.Priority)
            .ThenBy(expert => expert.Id, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return Task.FromResult<IReadOnlyList<IExpert>>(ordered);
    }
}
