using System.Text.Json;

namespace LocalAI.CloudInterface;

public static class JsonExpertPermissionLoader
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    public static async Task<IReadOnlyList<ExpertPermissionPolicy>> LoadAsync(
        IExpertPermissionStore store,
        string path)
    {
        ArgumentNullException.ThrowIfNull(store);

        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Expert permission JSON path is required.", nameof(path));
        }

        await using var stream = File.OpenRead(path);
        var document = await JsonSerializer.DeserializeAsync<ExpertPermissionDocument>(stream, SerializerOptions)
            .ConfigureAwait(false);

        var policies = new List<ExpertPermissionPolicy>();
        foreach (var entry in document?.Policies ?? [])
        {
            var policy = entry.ToPolicy();
            if (string.IsNullOrWhiteSpace(policy.ExpertId))
            {
                continue;
            }

            await store.SetAsync(policy).ConfigureAwait(false);
            policies.Add(policy);
        }

        return policies;
    }
}
