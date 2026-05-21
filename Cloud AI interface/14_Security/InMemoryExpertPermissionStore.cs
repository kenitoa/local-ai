using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryExpertPermissionStore : IExpertPermissionStore
{
    private readonly ConcurrentDictionary<string, ExpertPermissions> permissions = new(StringComparer.OrdinalIgnoreCase);
    private readonly ExpertPermissions defaultPermissions = new();

    public Task SetAsync(ExpertPermissionPolicy policy)
    {
        ArgumentNullException.ThrowIfNull(policy);

        if (string.IsNullOrWhiteSpace(policy.ExpertId))
        {
            throw new ArgumentException("Expert id is required.", nameof(policy));
        }

        permissions[policy.ExpertId] = policy.Permissions;
        return Task.CompletedTask;
    }

    public Task<ExpertPermissions> GetAsync(string expertId)
    {
        if (string.IsNullOrWhiteSpace(expertId)
            || !permissions.TryGetValue(expertId, out var expertPermissions))
        {
            return Task.FromResult(defaultPermissions);
        }

        return Task.FromResult(expertPermissions);
    }
}
