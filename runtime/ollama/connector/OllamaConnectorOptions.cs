namespace LocalAI.OllamaConnector;

public sealed class OllamaConnectorOptions
{
    public string ModelId { get; init; } = "llama3.1";
    public string Endpoint { get; init; } = "http://localhost:11434";
    public string ServiceId { get; init; } = "local-ollama";
    public int TimeoutSeconds { get; init; } = 180;
    public bool EnableFunctionCalling { get; init; } = true;
    public OllamaConnectorMode Mode { get; init; } = OllamaConnectorMode.NativeOllama;
}
