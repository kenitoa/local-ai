using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

namespace LocalAI.OllamaConnector;

public sealed class SemanticKernelOllamaConnector : IOllamaConnector
{
    private readonly OllamaConnectorOptions _options;

    public SemanticKernelOllamaConnector(OllamaConnectorOptions options)
    {
        _options = options;
    }

    public Kernel CreateKernel(Action<IKernelBuilder>? configureBuilder = null)
    {
        var builder = Kernel.CreateBuilder();
        var httpClient = CreateHttpClient();

#pragma warning disable SKEXP0070
        if (_options.Mode == OllamaConnectorMode.NativeOllama)
        {
            builder.AddOllamaChatCompletion(
                modelId: _options.ModelId,
                httpClient: httpClient,
                serviceId: _options.ServiceId);
        }
        else
        {
#pragma warning disable SKEXP0010
            builder.AddOpenAIChatCompletion(
                modelId: _options.ModelId,
                endpoint: CreateOpenAICompatibleEndpoint(),
                apiKey: "ollama",
                serviceId: _options.ServiceId,
                httpClient: httpClient);
#pragma warning restore SKEXP0010
        }
#pragma warning restore SKEXP0070

        configureBuilder?.Invoke(builder);

        return builder.Build();
    }

    public IChatCompletionService CreateChatCompletionService(Kernel kernel)
    {
        return kernel.Services.GetRequiredService<IChatCompletionService>();
    }

    public async Task<bool> CheckConnectionAsync(CancellationToken cancellationToken = default)
    {
        using var httpClient = CreateHealthHttpClient();

        try
        {
            using var response = await httpClient.GetAsync("/api/tags", cancellationToken);
            return response.IsSuccessStatusCode;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch
        {
            return false;
        }
    }

    public async Task<bool> CheckModelInstalledAsync(CancellationToken cancellationToken = default)
    {
        return await HasModelAsync(_options.ModelId, cancellationToken);
    }

    public async Task<bool> HasModelAsync(string modelName, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(modelName))
        {
            return false;
        }

        var models = await GetInstalledModelsAsync(cancellationToken);
        return models.Any(model =>
            model.Equals(modelName, StringComparison.OrdinalIgnoreCase) ||
            model.StartsWith($"{modelName}:", StringComparison.OrdinalIgnoreCase));
    }

    public async Task<IReadOnlyList<string>> GetInstalledModelsAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var (models, _) = await FetchInstalledModelsAsync(cancellationToken);
            return models;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch
        {
            return Array.Empty<string>();
        }
    }

    public async Task<OllamaHealthCheckResult> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var connected = await CheckConnectionAsync(cancellationToken);
            if (!connected)
            {
                return new OllamaHealthCheckResult(
                    false,
                    false,
                    _options.Endpoint,
                    _options.ModelId,
                    Array.Empty<string>(),
                    "Ollama server is not reachable.");
            }

            var (models, modelListError) = await FetchInstalledModelsAsync(cancellationToken);
            if (modelListError is not null)
            {
                return new OllamaHealthCheckResult(
                    true,
                    false,
                    _options.Endpoint,
                    _options.ModelId,
                    models,
                    modelListError);
            }

            var modelInstalled = ModelListContains(models, _options.ModelId);

            return new OllamaHealthCheckResult(
                true,
                modelInstalled,
                _options.Endpoint,
                _options.ModelId,
                models,
                modelInstalled ? null : $"Model '{_options.ModelId}' is not installed.");
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            return new OllamaHealthCheckResult(
                false,
                false,
                _options.Endpoint,
                _options.ModelId,
                Array.Empty<string>(),
                ex.Message);
        }
    }

    private async Task<(IReadOnlyList<string> Models, string? Error)> FetchInstalledModelsAsync(CancellationToken cancellationToken)
    {
        using var httpClient = CreateHealthHttpClient();

        try
        {
            await using var stream = await httpClient.GetStreamAsync("/api/tags", cancellationToken);
            using var document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);

            if (!document.RootElement.TryGetProperty("models", out var models) ||
                models.ValueKind != JsonValueKind.Array)
            {
                return (Array.Empty<string>(), "Ollama /api/tags response did not contain a models array.");
            }

            var result = new List<string>();
            foreach (var model in models.EnumerateArray())
            {
                if (model.TryGetProperty("name", out var name) &&
                    name.ValueKind == JsonValueKind.String &&
                    !string.IsNullOrWhiteSpace(name.GetString()))
                {
                    result.Add(name.GetString()!);
                }
            }

            return (result, null);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            return (Array.Empty<string>(), ex.Message);
        }
    }

    private static bool ModelListContains(IReadOnlyList<string> models, string modelName)
    {
        return models.Any(model =>
            model.Equals(modelName, StringComparison.OrdinalIgnoreCase) ||
            model.StartsWith($"{modelName}:", StringComparison.OrdinalIgnoreCase));
    }

    private HttpClient CreateHttpClient()
    {
        return new HttpClient
        {
            BaseAddress = new Uri(_options.Endpoint),
            Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds)
        };
    }

    private HttpClient CreateHealthHttpClient()
    {
        return new HttpClient
        {
            BaseAddress = new Uri(_options.Endpoint),
            Timeout = TimeSpan.FromSeconds(5)
        };
    }

    private Uri CreateOpenAICompatibleEndpoint()
    {
        var endpoint = _options.Endpoint.TrimEnd('/');
        if (!endpoint.EndsWith("/v1", StringComparison.OrdinalIgnoreCase))
        {
            endpoint += "/v1";
        }

        return new Uri(endpoint);
    }
}
