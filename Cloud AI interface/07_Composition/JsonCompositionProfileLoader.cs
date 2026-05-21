using System.Text.Json;

namespace LocalAI.CloudInterface;

public static class JsonCompositionProfileLoader
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    public static async Task<IReadOnlyList<CompositionProfile>> LoadAsync(
        ICompositionProfileRegistry registry,
        string path)
    {
        ArgumentNullException.ThrowIfNull(registry);

        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Composition profile JSON path is required.", nameof(path));
        }

        await using var stream = File.OpenRead(path);
        var document = await JsonSerializer.DeserializeAsync<CompositionProfileDocument>(stream, SerializerOptions)
            .ConfigureAwait(false);

        var registered = new List<CompositionProfile>();
        foreach (var entry in document?.Compositions ?? [])
        {
            var profile = entry.ToProfile();
            if (string.IsNullOrWhiteSpace(profile.CompositionId))
            {
                continue;
            }

            await registry.RegisterAsync(profile).ConfigureAwait(false);
            registered.Add(profile);
        }

        return registered;
    }
}
