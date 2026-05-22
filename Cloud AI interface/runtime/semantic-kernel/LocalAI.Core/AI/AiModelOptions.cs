using LocalAI.OllamaConnector;

namespace LocalAI.Core.AI;

public sealed class AiModelOptions
{
    public string Provider { get; set; } = "Ollama";
    public string ModelId { get; set; } = "llama3.1";
    public string Endpoint { get; set; } = "http://localhost:11434";
    public string ServiceId { get; set; } = "local-ollama";
    public int TimeoutSeconds { get; set; } = 180;
    public bool EnableFunctionCalling { get; set; } = true;
    public string? ApiKey { get; set; }

    public OllamaConnectorOptions ToOllamaConnectorOptions()
    {
        return new OllamaConnectorOptions
        {
            ModelId = ModelId,
            Endpoint = Endpoint,
            ServiceId = ServiceId,
            TimeoutSeconds = TimeoutSeconds,
            EnableFunctionCalling = EnableFunctionCalling,
            Mode = Provider.Equals("OpenAICompatible", StringComparison.OrdinalIgnoreCase)
                ? OllamaConnectorMode.OpenAICompatible
                : OllamaConnectorMode.NativeOllama
        };
    }
}
