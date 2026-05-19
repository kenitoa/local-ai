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
        var prompt = promptManager.BuildUserPrompt(userMessage);
        var modelResponse = await ollamaClient.GenerateAsync(model, prompt, cancellationToken);
        session.Add("assistant", modelResponse);

        var pluginResult = pluginRegistry.Invoke("time", "");

        return new FirstPassResult(
            semanticKernel,
            ollama,
            modelResponse,
            session.Messages.Count,
            pluginResult);
    }
}

public sealed record FirstPassResult(
    string SemanticKernel,
    string Ollama,
    string ModelResponse,
    int MessageCount,
    string PluginResult);
