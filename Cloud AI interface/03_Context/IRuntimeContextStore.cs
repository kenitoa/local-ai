namespace LocalAI.CloudInterface;

public interface IRuntimeContextStore
{
    Task<RuntimeContext> GetOrCreateAsync(string sessionId);
    Task SaveAsync(RuntimeContext context);
    Task AddMessageAsync(string sessionId, Message message);
    Task AddExpertResultAsync(string sessionId, ExpertResult result);
    Task AddToolResultAsync(string sessionId, ToolResult result);
    Task AddVectorMemoryAsync(string sessionId, VectorMemoryItem memory);
    Task AddExecutionHistoryAsync(string sessionId, ExecutionHistoryEntry entry);
    Task SetWorkingMemoryAsync(string sessionId, string key, object value);
    Task SetUserMemoryAsync(string sessionId, string key, object value);
}
