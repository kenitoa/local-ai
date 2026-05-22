using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace AspNetAiApi;

public sealed class OllamaClient(HttpClient httpClient)
{
    private static readonly TimeSpan StatusTimeout = TimeSpan.FromSeconds(2);

    public async Task<string> CheckAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(StatusTimeout);
            using var response = await httpClient.GetAsync("/api/tags", timeout.Token);
            response.EnsureSuccessStatusCode();
            return "connected";
        }
        catch (Exception ex)
        {
            return $"failed: {ex.Message}";
        }
    }

    public async Task<IReadOnlyList<string>> ListModelsAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(StatusTimeout);
            var response = await httpClient.GetFromJsonAsync<OllamaTagsResponse>("/api/tags", timeout.Token);
            var models = response?.Models?.Select(model => model.Name).Where(name => !string.IsNullOrWhiteSpace(name)).ToList();
            return models is { Count: > 0 } ? models : ["llama3.2"];
        }
        catch
        {
            return ["llama3.2"];
        }
    }

    public async Task<OllamaResult> GenerateAsync(
        string model,
        string prompt,
        CancellationToken cancellationToken)
    {
        try
        {
            using var response = await httpClient.PostAsJsonAsync(
                "/api/generate",
                new OllamaGenerateRequest(model, prompt, false),
                cancellationToken);

            response.EnsureSuccessStatusCode();

            var payload = await response.Content.ReadFromJsonAsync<OllamaGenerateResponse>(
                cancellationToken: cancellationToken);

            var answer = payload?.Response?.Trim();
            if (string.IsNullOrWhiteSpace(answer))
            {
                return new OllamaResult(false, "empty response");
            }

            return new OllamaResult(true, answer);
        }
        catch (Exception ex)
        {
            return new OllamaResult(false, ex.Message);
        }
    }
}

public sealed record OllamaResult(bool Success, string Text);

public sealed record OllamaTagsResponse(
    [property: JsonPropertyName("models")] IReadOnlyList<OllamaModel>? Models);

public sealed record OllamaModel(
    [property: JsonPropertyName("name")] string Name);

public sealed record OllamaGenerateRequest(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("prompt")] string Prompt,
    [property: JsonPropertyName("stream")] bool Stream);

public sealed record OllamaGenerateResponse(
    [property: JsonPropertyName("response")] string? Response);
