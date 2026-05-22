using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryRuntimeContextStore : IRuntimeContextStore
{
    private readonly ConcurrentDictionary<string, RuntimeContext> contexts = new(StringComparer.OrdinalIgnoreCase);

    public Task<RuntimeContext> GetOrCreateAsync(string sessionId)
    {
        var normalizedSessionId = NormalizeSessionId(sessionId);
        var context = contexts.GetOrAdd(normalizedSessionId, id => new RuntimeContext { SessionId = id });
        return Task.FromResult(context);
    }

    public Task SaveAsync(RuntimeContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        var normalizedSessionId = NormalizeSessionId(context.SessionId);
        contexts[normalizedSessionId] = context;
        return Task.CompletedTask;
    }

    public async Task AddMessageAsync(string sessionId, Message message)
    {
        ArgumentNullException.ThrowIfNull(message);

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.Conversation.Add(message);
        }
    }

    public async Task AddExpertResultAsync(string sessionId, ExpertResult result)
    {
        ArgumentNullException.ThrowIfNull(result);

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.PreviousResults.Add(result);
        }
    }

    public async Task AddToolResultAsync(string sessionId, ToolResult result)
    {
        ArgumentNullException.ThrowIfNull(result);

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.ToolResults.Add(result);
        }
    }

    public async Task AddVectorMemoryAsync(string sessionId, VectorMemoryItem memory)
    {
        ArgumentNullException.ThrowIfNull(memory);

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.VectorMemory.Add(memory);
        }
    }

    public async Task AddExecutionHistoryAsync(string sessionId, ExecutionHistoryEntry entry)
    {
        ArgumentNullException.ThrowIfNull(entry);

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.ExecutionHistory.Add(entry);
        }
    }

    public async Task SetWorkingMemoryAsync(string sessionId, string key, object value)
    {
        if (string.IsNullOrWhiteSpace(key))
        {
            throw new ArgumentException("Working memory key is required.", nameof(key));
        }

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.WorkingMemory[key] = value;
        }
    }

    public async Task SetUserMemoryAsync(string sessionId, string key, object value)
    {
        if (string.IsNullOrWhiteSpace(key))
        {
            throw new ArgumentException("User memory key is required.", nameof(key));
        }

        var context = await GetOrCreateAsync(sessionId).ConfigureAwait(false);
        lock (context)
        {
            context.UserMemory[key] = value;
        }
    }

    private static string NormalizeSessionId(string sessionId)
    {
        return string.IsNullOrWhiteSpace(sessionId)
            ? Guid.NewGuid().ToString("N")
            : sessionId.Trim();
    }
}
