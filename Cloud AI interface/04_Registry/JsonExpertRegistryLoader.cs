using System.Text.Json;

namespace LocalAI.CloudInterface;

public static class JsonExpertRegistryLoader
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    public static async Task<IReadOnlyList<IExpert>> LoadAsync(
        IExpertRegistry registry,
        string path,
        Func<ExpertProfile, IExpert>? expertFactory = null)
    {
        ArgumentNullException.ThrowIfNull(registry);

        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Registry JSON path is required.", nameof(path));
        }

        await using var stream = File.OpenRead(path);
        var document = await JsonSerializer.DeserializeAsync<ExpertRegistryDocument>(stream, SerializerOptions)
            .ConfigureAwait(false);

        var registered = new List<IExpert>();
        foreach (var entry in document?.Experts ?? [])
        {
            var profile = entry.ToProfile();
            if (string.IsNullOrWhiteSpace(profile.Id))
            {
                continue;
            }

            var expert = expertFactory?.Invoke(profile) ?? new RegisteredExpert(profile);
            await registry.RegisterAsync(expert).ConfigureAwait(false);
            registered.Add(expert);
        }

        return registered;
    }
}
