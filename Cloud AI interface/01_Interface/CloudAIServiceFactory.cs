namespace LocalAI.CloudInterface;

public static class CloudAIServiceFactory
{
    public static async Task<CloudAIService> CreateAsync(CloudAIServiceOptions? options = null)
    {
        options ??= new CloudAIServiceOptions();
        var resolvedOptions = ResolveDefaultPaths(options);

        var expertRegistry = new InMemoryExpertRegistry();
        var lifecycleManager = new InMemoryExpertLifecycleManager(
            expertRegistry,
            [
                new SemanticKernelOllamaRuntimeAdapter(),
                new LocalModelFileRuntimeAdapter(),
                new DefaultExpertRuntimeAdapter()
            ]);
        var permissionStore = new InMemoryExpertPermissionStore();
        var compositionRegistry = new InMemoryCompositionProfileRegistry();
        var fallbackChains = Array.Empty<FallbackChainProfile>();
        var traceSinks = new List<ITraceSink> { new InMemoryTraceSink() };

        if (!string.IsNullOrWhiteSpace(resolvedOptions.ExpertRegistryPath))
        {
            await JsonExpertLifecycleLoader.AttachFromJsonAsync(lifecycleManager, resolvedOptions.ExpertRegistryPath)
                .ConfigureAwait(false);
        }

        foreach (var definition in new LocalModelCatalog().Discover(resolvedOptions))
        {
            await lifecycleManager.AttachAsync(definition).ConfigureAwait(false);
        }

        if (!string.IsNullOrWhiteSpace(resolvedOptions.ExpertPermissionsPath))
        {
            await JsonExpertPermissionLoader.LoadAsync(permissionStore, resolvedOptions.ExpertPermissionsPath)
                .ConfigureAwait(false);
        }

        if (!string.IsNullOrWhiteSpace(resolvedOptions.CompositionProfilesPath))
        {
            await JsonCompositionProfileLoader.LoadAsync(compositionRegistry, resolvedOptions.CompositionProfilesPath)
                .ConfigureAwait(false);
        }

        if (!string.IsNullOrWhiteSpace(resolvedOptions.FallbackChainsPath))
        {
            fallbackChains = (await JsonFallbackChainLoader.LoadAsync(resolvedOptions.FallbackChainsPath).ConfigureAwait(false)).ToArray();
        }

        if (!string.IsNullOrWhiteSpace(resolvedOptions.TraceJsonlPath))
        {
            traceSinks.Add(new JsonlTraceSink(resolvedOptions.TraceJsonlPath));
        }

        var selfOptimizer = resolvedOptions.EnableSelfOptimization ? new SelfOptimizer() : null;
        var scoringRouter = new ScoringRouter();
        var profileRouter = new CompositionProfileRouter(compositionRegistry, fallbackRouter: scoringRouter);
        var router = CreateRouter(resolvedOptions, compositionRegistry, profileRouter, selfOptimizer);
        var executionEngine = new ParallelExecutionEngine(
            expertRegistry,
            permissionStore: permissionStore);

        return new CloudAIService(
            new DefaultCloudAIRequestNormalizer(),
            new DefaultSharedContextLoader(),
            expertRegistry,
            router,
            executionEngine,
            new ScoreBasedAggregator(),
            new RuleBasedVerifier(),
            new RuleBasedRecoveryPolicy(fallbackChains),
            new TraceRecorder(traceSinks),
            new DefaultMemoryUpdater(),
            selfOptimizer);
    }

    private static CloudAIServiceOptions ResolveDefaultPaths(CloudAIServiceOptions options)
    {
        var configurationDirectory = Path.Combine(AppContext.BaseDirectory, "Configuration");

        return new CloudAIServiceOptions
        {
            ExpertRegistryPath = ResolvePath(options.ExpertRegistryPath, configurationDirectory, "expert-registry.json"),
            CompositionProfilesPath = ResolvePath(options.CompositionProfilesPath, configurationDirectory, "composition-profiles.json"),
            FallbackChainsPath = ResolvePath(options.FallbackChainsPath, configurationDirectory, "fallback-chains.json"),
            ExpertPermissionsPath = ResolvePath(options.ExpertPermissionsPath, configurationDirectory, "expert-permissions.json"),
            TraceJsonlPath = options.TraceJsonlPath,
            LocalModelRootPath = ResolveDirectory(options.LocalModelRootPath, "local LLM model"),
            OllamaModelStorePath = ResolveDirectory(options.OllamaModelStorePath, Path.Combine("runtime", "ollama", "server", "models")),
            OllamaEndpoint = string.IsNullOrWhiteSpace(options.OllamaEndpoint) ? "http://localhost:11434" : options.OllamaEndpoint,
            DefaultOllamaModelId = string.IsNullOrWhiteSpace(options.DefaultOllamaModelId) ? "llama3.1" : options.DefaultOllamaModelId,
            EnableLocalModelDiscovery = options.EnableLocalModelDiscovery,
            MvpLevel = options.MvpLevel,
            EnableSelfOptimization = options.EnableSelfOptimization
        };
    }

    private static string? ResolvePath(string? explicitPath, string configurationDirectory, string fileName)
    {
        if (!string.IsNullOrWhiteSpace(explicitPath))
        {
            return explicitPath;
        }

        var defaultPath = Path.Combine(configurationDirectory, fileName);
        return File.Exists(defaultPath) ? defaultPath : null;
    }

    private static string? ResolveDirectory(string? explicitPath, string relativeDirectory)
    {
        if (!string.IsNullOrWhiteSpace(explicitPath))
        {
            return explicitPath;
        }

        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, relativeDirectory);
            if (Directory.Exists(candidate))
            {
                return candidate;
            }

            current = current.Parent;
        }

        var workingDirectoryCandidate = Path.Combine(Directory.GetCurrentDirectory(), relativeDirectory);
        return Directory.Exists(workingDirectoryCandidate) ? workingDirectoryCandidate : null;
    }

    private static IRouter CreateRouter(
        CloudAIServiceOptions options,
        ICompositionProfileRegistry compositionRegistry,
        IRouter profileRouter,
        ISelfOptimizer? selfOptimizer)
    {
        if (options.EnableSelfOptimization && selfOptimizer is not null)
        {
            return new SelfOptimizingRouter(selfOptimizer, compositionRegistry, fallbackRouter: profileRouter);
        }

        if (options.MvpLevel >= 4)
        {
            return profileRouter;
        }

        if (options.MvpLevel >= 2)
        {
            return profileRouter;
        }

        return new RuleBasedRouter();
    }
}
