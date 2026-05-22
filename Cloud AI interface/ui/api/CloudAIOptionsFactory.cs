using LocalAI.CloudInterface;

namespace AspNetAiApi;

internal static class CloudAIOptionsFactory
{
    public static CloudAIServiceOptions Create()
    {
        var root = FindRepositoryRoot();
        return new CloudAIServiceOptions
        {
            ExpertRegistryPath = Combine(root, "Configuration", "expert-registry.json"),
            CompositionProfilesPath = Combine(root, "Configuration", "composition-profiles.json"),
            FallbackChainsPath = Combine(root, "Configuration", "fallback-chains.json"),
            ExpertPermissionsPath = Combine(root, "Configuration", "expert-permissions.json"),
            LocalModelRootPath = Combine(root, "local LLM model"),
            OllamaModelStorePath = Combine(root, "runtime", "ollama", "server", "models"),
            MvpLevel = 4
        };
    }

    public static string? RepositoryRoot => FindRepositoryRoot();

    private static string? FindRepositoryRoot()
    {
        var current = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "CloudAI.Interface.csproj")) &&
                Directory.Exists(Path.Combine(current.FullName, "runtime")))
            {
                return current.FullName;
            }

            var sourceRoot = Path.Combine(current.FullName, "Cloud AI interface");
            if (File.Exists(Path.Combine(sourceRoot, "CloudAI.Interface.csproj")) &&
                Directory.Exists(Path.Combine(sourceRoot, "runtime")))
            {
                return sourceRoot;
            }

            current = current.Parent;
        }

        return null;
    }

    private static string? Combine(string? root, params string[] parts)
    {
        return root is null ? null : Path.Combine([root, .. parts]);
    }
}
