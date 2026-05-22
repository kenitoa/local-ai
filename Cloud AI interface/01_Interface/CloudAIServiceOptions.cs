namespace LocalAI.CloudInterface;

public sealed class CloudAIServiceOptions
{
    public string? ExpertRegistryPath { get; init; }
    public string? CompositionProfilesPath { get; init; }
    public string? FallbackChainsPath { get; init; }
    public string? ExpertPermissionsPath { get; init; }
    public string? TraceJsonlPath { get; init; }
    public string? LocalModelRootPath { get; init; }
    public string? OllamaModelStorePath { get; init; }
    public string OllamaEndpoint { get; init; } = "http://localhost:11434";
    public string DefaultOllamaModelId { get; init; } = "llama3.1";
    public bool EnableLocalModelDiscovery { get; init; } = true;
    public int MvpLevel { get; init; } = 2;
    public bool EnableSelfOptimization { get; init; }
}
