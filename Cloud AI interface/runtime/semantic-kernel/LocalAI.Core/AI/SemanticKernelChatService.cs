using System.Collections.Concurrent;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

namespace LocalAI.Core.AI;

public sealed class SemanticKernelChatService(
    Kernel kernel,
    IChatSessionStore sessionStore,
    AiModelOptions modelOptions) : IChatService, IStreamingChatService
{
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _sessionLocks = new();

    public async Task<ChatResponse> SendAsync(
        ChatRequest request,
        CancellationToken cancellationToken = default)
    {
        var sessionId = NormalizeSessionId(request.SessionId);
        var sessionLock = GetSessionLock(sessionId);
        await sessionLock.WaitAsync(cancellationToken);

        try
        {
            var history = CloneHistory(sessionStore.GetOrCreate(sessionId));
            var session = new ChatSession(
                kernel,
                history,
                ChatExecutionSettings.Create(modelOptions.EnableFunctionCalling));

            var answer = await session.SendAsync(request.Message, cancellationToken);
            sessionStore.Save(sessionId, session.History);

            return new ChatResponse(
                sessionId,
                answer,
                DateTime.Now);
        }
        finally
        {
            sessionLock.Release();
        }
    }

    public async IAsyncEnumerable<string> StreamAsync(
        ChatRequest request,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var sessionId = NormalizeSessionId(request.SessionId);
        var sessionLock = GetSessionLock(sessionId);
        await sessionLock.WaitAsync(cancellationToken);

        try
        {
            var history = CloneHistory(sessionStore.GetOrCreate(sessionId));
            var session = new ChatSession(
                kernel,
                history,
                ChatExecutionSettings.Create(modelOptions.EnableFunctionCalling));

            await foreach (var chunk in session.StreamAsync(request.Message, cancellationToken))
            {
                yield return chunk;
            }

            sessionStore.Save(sessionId, session.History);
        }
        finally
        {
            sessionLock.Release();
        }
    }

    private SemaphoreSlim GetSessionLock(string sessionId)
    {
        return _sessionLocks.GetOrAdd(sessionId, _ => new SemaphoreSlim(1, 1));
    }

    private static ChatHistory CloneHistory(ChatHistory history)
    {
        var clone = new ChatHistory();
        foreach (var message in history)
        {
            clone.Add(message);
        }

        return clone;
    }

    private static string NormalizeSessionId(string sessionId)
    {
        return string.IsNullOrWhiteSpace(sessionId)
            ? Guid.NewGuid().ToString("N")
            : sessionId.Trim();
    }
}
