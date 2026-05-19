using LocalAI.Core.AI;
using LocalAI.OllamaConnector;
using SystemConsole = System.Console;

namespace LocalAI.Console.UI;

public sealed class ConsoleChatUI
{
    private readonly AiModelOptions _modelOptions;
    private readonly IOllamaConnector _connector;

    public ConsoleChatUI(AiModelOptions? modelOptions = null, IOllamaConnector? connector = null)
    {
        _modelOptions = modelOptions ?? new AiModelOptions();
        _connector = connector ?? new SemanticKernelOllamaConnector(_modelOptions.ToOllamaConnectorOptions());
    }

    public async Task RunAsync(CancellationToken cancellationToken = default)
    {
        var health = await _connector.CheckHealthAsync(cancellationToken);

        WriteHeader(health);

        if (!health.IsReachable)
        {
            SystemConsole.WriteLine("Ollama 서버가 실행 중이 아닙니다.");
            SystemConsole.WriteLine(@"먼저 Ollama Local Server에서 실행하세요: .\start-server.ps1 -Background");
            return;
        }

        if (!health.ModelInstalled)
        {
            SystemConsole.WriteLine($"Ollama 모델이 설치되어 있지 않습니다: {_modelOptions.ModelId}");
            SystemConsole.WriteLine($"설치 명령: ollama pull {_modelOptions.ModelId}");
            return;
        }

        var kernel = KernelFactory.Create(_connector);
        var chat = new ChatSession(kernel, ChatExecutionSettings.Create(_modelOptions.EnableFunctionCalling));

        SystemConsole.WriteLine("종료하려면 exit 입력");
        await RunChatLoopAsync(chat, cancellationToken);
    }

    private void WriteHeader(OllamaHealthCheckResult health)
    {
        SystemConsole.WriteLine("Semantic Kernel + Ollama 로컬 인터페이스");
        SystemConsole.WriteLine($"Endpoint: {_modelOptions.Endpoint}");
        SystemConsole.WriteLine($"Model: {_modelOptions.ModelId}");
        SystemConsole.WriteLine($"Ollama: {(health.IsReachable ? "connected" : "not reachable")}");
    }

    private static async Task RunChatLoopAsync(ChatSession chat, CancellationToken cancellationToken)
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
                SystemConsole.Write("\nAI: ");
                await foreach (var token in chat.StreamAsync(input, cancellationToken))
                {
                    SystemConsole.Write(token);
                }

                SystemConsole.WriteLine();
            }
            catch (Exception ex)
            {
                SystemConsole.WriteLine($"\nERROR: {ex.Message}");
            }
        }
    }
}
