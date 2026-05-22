using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

namespace LocalAI.OllamaConnector;

public interface IOllamaConnector
{
    Kernel CreateKernel(Action<IKernelBuilder>? configureBuilder = null);
    IChatCompletionService CreateChatCompletionService(Kernel kernel);
    Task<bool> CheckConnectionAsync(CancellationToken cancellationToken = default);
    Task<bool> CheckModelInstalledAsync(CancellationToken cancellationToken = default);
    Task<bool> HasModelAsync(string modelName, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<string>> GetInstalledModelsAsync(CancellationToken cancellationToken = default);
    Task<OllamaHealthCheckResult> CheckHealthAsync(CancellationToken cancellationToken = default);
}

public sealed record OllamaHealthCheckResult(
    bool IsReachable,
    bool ModelInstalled,
    string Endpoint,
    string ModelId,
    IReadOnlyList<string> InstalledModels,
    string? Error);
