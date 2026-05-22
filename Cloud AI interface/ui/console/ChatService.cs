using LocalAI.CloudInterface;

namespace ConsoleValidation;

public sealed class ChatService(
    KernelFactory kernelFactory,
    PromptManager promptManager,
    PluginRegistry pluginRegistry,
    OllamaClient ollamaClient,
    ConsoleLogger logger)
{
    public async Task<FirstPassResult> RunFirstPassAsync(
        string model,
        string userMessage,
        CancellationToken cancellationToken)
    {
        var session = new ChatSession();

        var semanticKernel = kernelFactory.Create();
        session.Add("system", promptManager.SystemPrompt);
        session.Add("user", userMessage);
        logger.Info("ChatSession", "대화 기록을 세션에 추가했습니다.");

        var ollama = await ollamaClient.CheckConnectionAsync(cancellationToken);
        var cloudAi = await CloudAIServiceFactory.CreateAsync(CreateCloudAIOptions()).ConfigureAwait(false);
        var response = await cloudAi.InvokeAsync(new CloudAIRequest
        {
            RequestId = Guid.NewGuid().ToString("N"),
            UserId = "ui-console",
            Input = promptManager.BuildUserPrompt(userMessage),
            TaskType = "chat",
            SharedContext = new RuntimeContext { SessionId = "console-validation" },
            Options = new RuntimeOptions
            {
                PreferredExperts = [ToOllamaExpertId(model)],
                RequireVerification = true
            }
        });
        var modelResponse = response.Output;
        session.Add("assistant", modelResponse);

        var pluginResult = pluginRegistry.Invoke("time", "");

        return new FirstPassResult(
            semanticKernel,
            ollama,
            modelResponse,
            session.Messages.Count,
            pluginResult);
    }

    private static CloudAIServiceOptions CreateCloudAIOptions()
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

    private static string ToOllamaExpertId(string model)
    {
        var normalized = model.ToLowerInvariant()
            .Select(ch => char.IsLetterOrDigit(ch) ? ch : '-')
            .ToArray();
        var id = new string(normalized).Trim('-');

        while (id.Contains("--", StringComparison.Ordinal))
        {
            id = id.Replace("--", "-", StringComparison.Ordinal);
        }

        if (!id.EndsWith("-latest", StringComparison.OrdinalIgnoreCase) && !model.Contains(':', StringComparison.Ordinal))
        {
            id += "-latest";
        }

        return $"ollama-{id}";
    }
}

public sealed record FirstPassResult(
    string SemanticKernel,
    string Ollama,
    string ModelResponse,
    int MessageCount,
    string PluginResult);
