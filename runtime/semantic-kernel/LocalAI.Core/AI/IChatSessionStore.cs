using Microsoft.SemanticKernel.ChatCompletion;

namespace LocalAI.Core.AI;

public interface IChatSessionStore
{
    ChatHistory GetOrCreate(string sessionId);
    void Save(string sessionId, ChatHistory history);
    void Clear(string sessionId);
}
