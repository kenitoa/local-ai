using System.Collections.Concurrent;
using LocalAI.Core.Prompts;
using Microsoft.SemanticKernel.ChatCompletion;

namespace LocalAI.Core.AI;

public sealed class InMemoryChatSessionStore : IChatSessionStore
{
    private readonly ConcurrentDictionary<string, ChatHistory> _sessions = new();

    public ChatHistory GetOrCreate(string sessionId)
    {
        return _sessions.GetOrAdd(sessionId, _ =>
        {
            var history = new ChatHistory();
            history.AddSystemMessage(SystemPrompts.DefaultAssistant);
            return history;
        });
    }

    public void Save(string sessionId, ChatHistory history)
    {
        _sessions[sessionId] = history;
    }

    public void Clear(string sessionId)
    {
        _sessions.TryRemove(sessionId, out _);
    }
}
