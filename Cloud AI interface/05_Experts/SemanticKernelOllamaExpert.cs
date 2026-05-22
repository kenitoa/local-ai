using System.Diagnostics;
using LocalAI.Core.AI;
using LocalAI.Core.Plugins;
using LocalAI.OllamaConnector;

namespace LocalAI.CloudInterface;

public sealed class SemanticKernelOllamaExpert : ExpertAdapterBase
{
    private readonly ExpertDefinition definition;
    private readonly string modelId;
    private readonly string endpoint;
    private readonly int timeoutSeconds;

    public SemanticKernelOllamaExpert(ExpertDefinition definition)
        : base(definition.Profile, request => InvokeSemanticKernelAsync(definition, request))
    {
        this.definition = definition;
        modelId = ReadSetting(definition, "modelId", definition.Profile.Id);
        endpoint = definition.Endpoint ?? ReadSetting(definition, "endpoint", "http://localhost:11434");
        timeoutSeconds = ReadIntSetting(definition, "timeoutSeconds", 180);
    }

    public async Task<OllamaExpertHealth> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        var stopwatch = Stopwatch.StartNew();
        var connector = new SemanticKernelOllamaConnector(CreateOptions(definition));
        var health = await connector.CheckHealthAsync(cancellationToken).ConfigureAwait(false);
        stopwatch.Stop();

        return new OllamaExpertHealth(
            health.IsReachable,
            health.ModelInstalled,
            health.Endpoint,
            health.ModelId,
            health.InstalledModels,
            health.Error,
            stopwatch.Elapsed.TotalMilliseconds);
    }

    private static async Task<ExpertResult> InvokeSemanticKernelAsync(
        ExpertDefinition definition,
        ExpertRequest request)
    {
        var modelOptions = CreateAiModelOptions(definition);
        var kernel = KernelFactory.Create(modelOptions, CreatePluginPermissions());
        var chatService = new SemanticKernelChatService(
            kernel,
            new InMemoryChatSessionStore(),
            modelOptions);

        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(modelOptions.TimeoutSeconds));
        var response = await chatService.SendAsync(
            new LocalAI.Core.AI.ChatRequest(
                request.SharedContext.SessionId,
                request.Input,
                modelOptions.ModelId),
            timeout.Token).ConfigureAwait(false);

        return new ExpertResult
        {
            ExpertId = definition.Profile.Id,
            Output = response.Message,
            Confidence = 0.82,
            Succeeded = !string.IsNullOrWhiteSpace(response.Message),
            IsJsonOutput = false,
            Metadata = new Dictionary<string, object>
            {
                ["provider"] = "ollama",
                ["modelId"] = modelOptions.ModelId,
                ["endpoint"] = modelOptions.Endpoint
            }
        };
    }

    private static AiModelOptions CreateAiModelOptions(ExpertDefinition definition)
    {
        return new AiModelOptions
        {
            Provider = "Ollama",
            ModelId = ReadSetting(definition, "modelId", definition.Profile.Id),
            Endpoint = definition.Endpoint ?? ReadSetting(definition, "endpoint", "http://localhost:11434"),
            ServiceId = ReadSetting(definition, "serviceId", $"cloud-ai-{definition.Profile.Id}"),
            TimeoutSeconds = ReadIntSetting(definition, "timeoutSeconds", 180),
            EnableFunctionCalling = ReadBoolSetting(definition, "enableFunctionCalling", true)
        };
    }

    private static OllamaConnectorOptions CreateOptions(ExpertDefinition definition)
    {
        return CreateAiModelOptions(definition).ToOllamaConnectorOptions();
    }

    private static PluginPermissionOptions CreatePluginPermissions()
    {
        return new PluginPermissionOptions
        {
            AllowCommandExecution = false,
            AllowFileDelete = false,
            AllowNasControl = false
        };
    }

    private static string ReadSetting(ExpertDefinition definition, string key, string fallback)
    {
        return definition.Settings.TryGetValue(key, out var value) && value is not null && !string.IsNullOrWhiteSpace(value.ToString())
            ? value.ToString()!
            : fallback;
    }

    private static int ReadIntSetting(ExpertDefinition definition, string key, int fallback)
    {
        return definition.Settings.TryGetValue(key, out var value) && int.TryParse(value?.ToString(), out var parsed)
            ? parsed
            : fallback;
    }

    private static bool ReadBoolSetting(ExpertDefinition definition, string key, bool fallback)
    {
        return definition.Settings.TryGetValue(key, out var value) && bool.TryParse(value?.ToString(), out var parsed)
            ? parsed
            : fallback;
    }
}

public sealed record OllamaExpertHealth(
    bool IsReachable,
    bool ModelInstalled,
    string Endpoint,
    string ModelId,
    IReadOnlyList<string> InstalledModels,
    string? Error,
    double LatencyMs);
