using ConsoleValidation;

var logger = new ConsoleLogger();
var prompts = new PromptManager();
var plugins = new PluginRegistry(logger);
var kernelFactory = new KernelFactory(logger);
using var httpClient = new HttpClient
{
    Timeout = TimeSpan.FromSeconds(8)
};
var chatService = new ChatService(
    kernelFactory,
    prompts,
    plugins,
    new OllamaClient(httpClient, logger),
    logger);

logger.Info("Console", "1차 검증을 시작합니다.");

try
{
    plugins.RegisterDefaults();

    var request = args.Length > 0
        ? string.Join(' ', args)
        : "Console 1차 검증입니다. 한 문장으로 응답하세요.";

    var model = Environment.GetEnvironmentVariable("OLLAMA_MODEL");
    if (string.IsNullOrWhiteSpace(model))
    {
        model = "llama3.2";
    }

    var result = await chatService.RunFirstPassAsync(model, request, CancellationToken.None);

    logger.Info("Summary", $"Semantic Kernel: {result.SemanticKernel}");
    logger.Info("Summary", $"Ollama: {result.Ollama}");
    logger.Info("Summary", $"Model response: {result.ModelResponse}");
    logger.Info("Summary", $"Dialog messages: {result.MessageCount}");
    logger.Info("Summary", $"Plugin call: {result.PluginResult}");
}
catch (Exception ex)
{
    logger.Error("Console", $"검증 중 예외가 발생했습니다. {ex.Message}");
    Environment.ExitCode = 1;
}
