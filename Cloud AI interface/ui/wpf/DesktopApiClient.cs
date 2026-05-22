using System.Net.Http;
using System.Net.Http.Json;

namespace WpfDesktopMvp;

public sealed class DesktopApiClient
{
    private readonly HttpClient httpClient = new()
    {
        Timeout = TimeSpan.FromSeconds(30)
    };

    public async Task<HealthResponse> GetHealthAsync(string baseUrl)
    {
        return await GetFromJsonAsync<HealthResponse>(baseUrl, "/api/health");
    }

    public async Task<IReadOnlyList<string>> GetModelsAsync(string baseUrl)
    {
        var response = await GetFromJsonAsync<ModelsResponse>(baseUrl, "/api/models");
        return response.Models.Count > 0
            ? response.Models
            : new[] { response.ConfiguredModel };
    }

    public async Task<NewSessionResponse> CreateSessionAsync(string baseUrl, string title)
    {
        return await PostAsJsonAsync<NewSessionResponse>(
            baseUrl,
            "/api/session",
            new NewSessionRequest(title));
    }

    public async Task<ChatResponse> SendChatAsync(
        string baseUrl,
        string? sessionId,
        string model,
        string message)
    {
        return await PostAsJsonAsync<ChatResponse>(
            baseUrl,
            "/api/chat",
            new ChatRequest(sessionId, model, message));
    }

    public async Task<ToolExecuteResponse> ExecuteToolAsync(string baseUrl, string name, string input)
    {
        return await PostAsJsonAsync<ToolExecuteResponse>(
            baseUrl,
            "/api/tools/execute",
            new ToolExecuteRequest(name, input));
    }

    private async Task<T> GetFromJsonAsync<T>(string baseUrl, string path)
    {
        var uri = BuildUri(baseUrl, path);
        var result = await httpClient.GetFromJsonAsync<T>(uri);
        return result ?? throw new InvalidOperationException("API returned an empty response.");
    }

    private async Task<T> PostAsJsonAsync<T>(string baseUrl, string path, object body)
    {
        var uri = BuildUri(baseUrl, path);
        using var response = await httpClient.PostAsJsonAsync(uri, body);
        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<T>();
        return result ?? throw new InvalidOperationException("API returned an empty response.");
    }

    private static Uri BuildUri(string baseUrl, string path)
    {
        if (!Uri.TryCreate(baseUrl.TrimEnd('/') + "/", UriKind.Absolute, out var root))
        {
            throw new InvalidOperationException("API Base URL is invalid.");
        }

        return new Uri(root, path.TrimStart('/'));
    }
}
