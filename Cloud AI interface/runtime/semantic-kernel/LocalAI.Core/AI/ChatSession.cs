using LocalAI.Core.Prompts;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

namespace LocalAI.Core.AI;

public class ChatSession
{
    private readonly Kernel _kernel;
    private readonly IChatCompletionService _chatService;
    private readonly ChatHistory _history;
    private readonly PromptExecutionSettings? _executionSettings;

    public ChatHistory History => _history;

    public ChatSession(Kernel kernel)
        : this(kernel, CreateDefaultHistory(), ChatExecutionSettings.CreateAutoFunctionCalling())
    {
    }

    public ChatSession(Kernel kernel, PromptExecutionSettings? executionSettings)
        : this(kernel, CreateDefaultHistory(), executionSettings)
    {
    }

    public ChatSession(
        Kernel kernel,
        ChatHistory history,
        PromptExecutionSettings? executionSettings)
    {
        _kernel = kernel;
        _chatService = kernel.GetRequiredService<IChatCompletionService>();
        _history = history;
        _executionSettings = executionSettings;
    }

    public async Task<string> SendAsync(string message, CancellationToken cancellationToken = default)
    {
        _history.AddUserMessage(message);

        var response = await _chatService.GetChatMessageContentAsync(
            _history,
            executionSettings: _executionSettings,
            kernel: _kernel,
            cancellationToken: cancellationToken);

        var content = response.Content ?? string.Empty;
        _history.AddAssistantMessage(content);

        return content;
    }

    public async IAsyncEnumerable<string> StreamAsync(
        string message,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _history.AddUserMessage(message);

        var chunks = new List<string>();
        await foreach (var chunk in _chatService.GetStreamingChatMessageContentsAsync(
            _history,
            executionSettings: _executionSettings,
            kernel: _kernel,
            cancellationToken: cancellationToken))
        {
            var content = chunk.Content ?? string.Empty;
            if (content.Length == 0)
            {
                continue;
            }

            chunks.Add(content);
            yield return content;
        }

        _history.AddAssistantMessage(string.Concat(chunks));
    }

    private static ChatHistory CreateDefaultHistory()
    {
        var history = new ChatHistory();
        history.AddSystemMessage(SystemPrompts.DefaultAssistant);
        return history;
    }
}
