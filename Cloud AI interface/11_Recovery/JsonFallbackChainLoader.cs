using System.Text.Json;

namespace LocalAI.CloudInterface;

public static class JsonFallbackChainLoader
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    public static async Task<IReadOnlyList<FallbackChainProfile>> LoadAsync(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Fallback chain JSON path is required.", nameof(path));
        }

        await using var stream = File.OpenRead(path);
        var document = await JsonSerializer.DeserializeAsync<FallbackChainDocument>(stream, SerializerOptions)
            .ConfigureAwait(false);

        return (document?.Chains ?? [])
            .Select(entry => entry.ToProfile())
            .Where(profile => !string.IsNullOrWhiteSpace(profile.Primary))
            .ToArray();
    }
}
