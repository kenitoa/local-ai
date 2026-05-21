using System.Text.Json;

namespace LocalAI.CloudInterface;

public static class JsonExpertLifecycleLoader
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    public static async Task<IReadOnlyList<ExpertDefinition>> AttachFromJsonAsync(
        IExpertLifecycleManager lifecycleManager,
        string path)
    {
        ArgumentNullException.ThrowIfNull(lifecycleManager);

        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Expert registry JSON path is required.", nameof(path));
        }

        await using var stream = File.OpenRead(path);
        var document = await JsonSerializer.DeserializeAsync<ExpertRegistryDocument>(stream, SerializerOptions)
            .ConfigureAwait(false);

        var attached = new List<ExpertDefinition>();
        foreach (var entry in document?.Experts ?? [])
        {
            var definition = ExpertDefinitionMapper.FromRegistryEntry(entry);
            if (string.IsNullOrWhiteSpace(definition.Profile.Id))
            {
                continue;
            }

            await lifecycleManager.AttachAsync(definition).ConfigureAwait(false);
            attached.Add(definition);
        }

        return attached;
    }
}
