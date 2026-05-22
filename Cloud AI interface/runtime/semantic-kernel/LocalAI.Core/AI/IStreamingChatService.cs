namespace LocalAI.Core.AI;

public interface IStreamingChatService
{
    IAsyncEnumerable<string> StreamAsync(ChatRequest request, CancellationToken cancellationToken = default);
}
