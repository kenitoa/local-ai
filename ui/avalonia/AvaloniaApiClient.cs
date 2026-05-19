using System.Net.Http;
using System.Net.Http.Json;

namespace AvaloniaCrossPlatformUi;

public sealed class AvaloniaApiClient
{
    private readonly HttpClient httpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(30)
    };

    public async Task<HealthResponse> GetHealthAsync(string apiBaseUrl)
    {
        var result = await httpClient.GetFromJsonAsync<HealthResponse>(BuildUri(apiBaseUrl, "/api/health"));
        return result ?? throw new InvalidOperationException("API returned an empty health response.");
    }

    public async Task<IReadOnlyList<string>> GetModelsAsync(string apiBaseUrl)
    {
        var result = await httpClient.GetFromJsonAsync<ModelsResponse>(BuildUri(apiBaseUrl, "/api/models"));
        return result?.Models ?? [];
    }

    public async Task<ChatResponse> SendChatAsync(
        string apiBaseUrl,
        string? sessionId,
        string model,
        string message)
    {
        using var response = await httpClient.PostAsJsonAsync(
            BuildUri(apiBaseUrl, "/api/chat"),
            new ChatRequest(sessionId, model, message));

        response.EnsureSuccessStatusCode();

        var result = await response.Content.ReadFromJsonAsync<ChatResponse>();
        return result ?? throw new InvalidOperationException("API returned an empty chat response.");
    }

    private static Uri BuildUri(string apiBaseUrl, string path)
    {
        if (!Uri.TryCreate(apiBaseUrl.TrimEnd('/') + "/", UriKind.Absolute, out var root))
        {
            throw new InvalidOperationException("API Base URL is invalid.");
        }

        return new Uri(root, path.TrimStart('/'));
    }
}

public sealed record HealthResponse(
    string Status,
    string Api,
    string Provider,
    string ModelId,
    string Endpoint,
    string ServiceId,
    int TimeoutSeconds,
    bool EnableFunctionCalling,
    bool ModelInstalled);

public sealed record ModelsResponse(
    IReadOnlyList<string> Models,
    string ConfiguredModel,
    bool OllamaReachable);

public sealed record ChatRequest(
    string? SessionId,
    string Model,
    string Message);

public sealed record ChatResponse(
    string SessionId,
    string Message,
    DateTime CreatedAt);
