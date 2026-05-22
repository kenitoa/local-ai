using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ConsoleValidation;

public sealed class OllamaClient(HttpClient httpClient, ConsoleLogger logger)
{
    private static readonly Uri BaseUri = new("http://localhost:11434");

    public async Task<string> CheckConnectionAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var response = await httpClient.GetAsync(new Uri(BaseUri, "/api/tags"), cancellationToken);
            response.EnsureSuccessStatusCode();
            logger.Info("Ollama", "Ollama 연결을 확인했습니다.");
            return "connected";
        }
        catch (Exception ex)
        {
            logger.Error("Ollama", $"연결 실패: {ex.Message}");
            return "failed";
        }
    }

    public async Task<string> GenerateAsync(string model, string prompt, CancellationToken cancellationToken)
    {
        try
        {
            using var response = await httpClient.PostAsJsonAsync(
                new Uri(BaseUri, "/api/generate"),
                new OllamaGenerateRequest(model, prompt, false),
                cancellationToken);

            response.EnsureSuccessStatusCode();

            var payload = await response.Content.ReadFromJsonAsync<OllamaGenerateResponse>(
                JsonOptions,
                cancellationToken);

            var answer = payload?.Response?.Trim();
            if (string.IsNullOrWhiteSpace(answer))
            {
                return "Ollama 응답이 비어 있습니다.";
            }

            logger.Info("Ollama", "모델 응답을 확인했습니다.");
            return answer;
        }
        catch (Exception ex)
        {
            logger.Error("Ollama", $"모델 응답 실패: {ex.Message}");
            return $"model-response-failed: {ex.Message}";
        }
    }

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
}

public sealed record OllamaGenerateRequest(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("prompt")] string Prompt,
    [property: JsonPropertyName("stream")] bool Stream);

public sealed record OllamaGenerateResponse(
    [property: JsonPropertyName("response")] string? Response);
