namespace AspNetAiApi;

public sealed class ChatService(
    SessionStore sessions,
    PromptManager prompts,
    KernelGateway kernelGateway)
{
    public async Task<ChatResponse> SendAsync(ChatRequest request, CancellationToken cancellationToken)
    {
        var session = sessions.GetOrCreate(request.SessionId);
        var model = string.IsNullOrWhiteSpace(request.Model) ? "llama3.2" : request.Model.Trim();
        var message = string.IsNullOrWhiteSpace(request.Message)
            ? "API 연결 검증 메시지입니다."
            : request.Message.Trim();

        session.Add("user", message);

        var prompt = prompts.BuildChatPrompt(session.Messages, message);
        var result = await kernelGateway.CompleteAsync(model, prompt, cancellationToken);

        session.Add("assistant", result.Text);

        return new ChatResponse(
            session.Id,
            model,
            result.Text,
            result.Source,
            session.Messages.Select(FromMessage).ToList());
    }

    public async IAsyncEnumerable<string> StreamAsync(
        ChatRequest request,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var response = await SendAsync(request, cancellationToken);
        var words = response.Response.Split(' ', StringSplitOptions.RemoveEmptyEntries);

        foreach (var word in words)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return word;
            await Task.Delay(60, cancellationToken);
        }
    }

    private static ChatMessageDto FromMessage(ChatMessage message)
    {
        return new ChatMessageDto(message.Role, message.Content, message.CreatedAt);
    }
}
