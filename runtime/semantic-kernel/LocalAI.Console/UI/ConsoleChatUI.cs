using LocalAI.CloudInterface;
using LocalAI.Core.AI;
using LocalAI.OllamaConnector;
using SystemConsole = System.Console;

namespace LocalAI.Console.UI;

public sealed class ConsoleChatUI
{
    private readonly AiModelOptions modelOptions;
    private readonly IOllamaConnector connector;
    private readonly Lazy<Task<ICloudAI>> cloudAi;

    public ConsoleChatUI(AiModelOptions? modelOptions = null, IOllamaConnector? connector = null)
    {
        this.modelOptions = modelOptions ?? new AiModelOptions();
        this.connector = connector ?? new SemanticKernelOllamaConnector(this.modelOptions.ToOllamaConnectorOptions());
        cloudAi = new Lazy<Task<ICloudAI>>(async () => await CloudAIServiceFactory.CreateAsync(CreateCloudOptions()).ConfigureAwait(false));
    }

    public async Task RunAsync(CancellationToken cancellationToken = default)
    {
        var health = await connector.CheckHealthAsync(cancellationToken);

        WriteHeader(health);

        if (!health.IsReachable)
        {
            SystemConsole.WriteLine("Ollama 서버가 실행 중이 아닙니다.");
            SystemConsole.WriteLine(@"먼저 Ollama Local Server에서 실행하세요: .\start-server.ps1 -Background");
            return;
        }

        if (!health.ModelInstalled)
        {
            SystemConsole.WriteLine($"Ollama 모델이 설치되어 있지 않습니다: {modelOptions.ModelId}");
            SystemConsole.WriteLine($"설치 명령: ollama pull {modelOptions.ModelId}");
            return;
        }

        SystemConsole.WriteLine("종료하려면 exit 입력");
        await RunChatLoopAsync(await cloudAi.Value.ConfigureAwait(false), cancellationToken);
    }

    private void WriteHeader(OllamaHealthCheckResult health)
    {
        SystemConsole.WriteLine("Cloud AI Interface + Semantic Kernel + Ollama");
        SystemConsole.WriteLine($"Endpoint: {modelOptions.Endpoint}");
        SystemConsole.WriteLine($"Model: {modelOptions.ModelId}");
        SystemConsole.WriteLine($"Ollama: {(health.IsReachable ? "connected" : "not reachable")}");
    }

    private async Task RunChatLoopAsync(ICloudAI cloudAiRuntime, CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            SystemConsole.Write("\nUser: ");
            var input = SystemConsole.ReadLine();

            if (string.IsNullOrWhiteSpace(input))
            {
                continue;
            }

            if (input.Equals("exit", StringComparison.OrdinalIgnoreCase))
            {
                break;
            }

            try
            {
                var response = await cloudAiRuntime.InvokeAsync(new CloudAIRequest
                {
                    RequestId = Guid.NewGuid().ToString("N"),
                    UserId = "local-ai-console",
                    Input = input,
                    TaskType = "chat",
                    SharedContext = new RuntimeContext { SessionId = "console" },
                    Options = new RuntimeOptions
                    {
                        PreferredExperts = [ToOllamaExpertId(modelOptions.ModelId)],
                        RequireVerification = true
                    }
                }).ConfigureAwait(false);

                SystemConsole.Write("\nAI: ");
                SystemConsole.WriteLine(response.Output);
            }
            catch (Exception ex)
            {
                SystemConsole.WriteLine($"\nERROR: {ex.Message}");
            }
        }
    }

    private CloudAIServiceOptions CreateCloudOptions()
    {
        var root = FindRepositoryRoot();
        return new CloudAIServiceOptions
        {
            ExpertRegistryPath = Combine(root, "Cloud AI interface", "Configuration", "expert-registry.json"),
            CompositionProfilesPath = Combine(root, "Cloud AI interface", "Configuration", "composition-profiles.json"),
            FallbackChainsPath = Combine(root, "Cloud AI interface", "Configuration", "fallback-chains.json"),
            ExpertPermissionsPath = Combine(root, "Cloud AI interface", "Configuration", "expert-permissions.json"),
            LocalModelRootPath = Combine(root, "local LLM model"),
            OllamaModelStorePath = Combine(root, "runtime", "ollama", "server", "models"),
            OllamaEndpoint = modelOptions.Endpoint,
            DefaultOllamaModelId = modelOptions.ModelId,
            MvpLevel = 4
        };
    }

    private static string? FindRepositoryRoot()
    {
        var current = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, "Cloud AI interface")) &&
                Directory.Exists(Path.Combine(current.FullName, "runtime")))
            {
                return current.FullName;
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
