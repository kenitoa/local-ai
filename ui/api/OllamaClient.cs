using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace AspNetAiApi;

public sealed class OllamaClient(HttpClient httpClient)
{
    public async Task<string> CheckAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var response = await httpClient.GetAsync("/api/tags", cancellationToken);
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
            var response = await httpClient.GetFromJsonAsync<OllamaTagsResponse>("/api/tags", cancellationToken);
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
