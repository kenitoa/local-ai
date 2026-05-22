using System.Collections.Concurrent;

namespace AspNetAiApi;

public sealed class SessionStore
{
    private readonly ConcurrentDictionary<string, ChatSession> sessions = new();

    public ChatSession Create(string? title)
    {
        var session = new ChatSession(title);
        sessions[session.Id] = session;
        return session;
    }

    public ChatSession GetOrCreate(string? sessionId)
    {
        if (!string.IsNullOrWhiteSpace(sessionId) &&
            sessions.TryGetValue(sessionId, out var existing))
        {
            return existing;
        }

        return Create("API chat");
    }
}

public sealed class ChatSession
{
    private readonly List<ChatMessage> messages = new();

    public ChatSession(string? title)
    {
        Id = Guid.NewGuid().ToString("N");
        Title = string.IsNullOrWhiteSpace(title) ? "Untitled session" : title.Trim();
        CreatedAt = DateTimeOffset.Now;
        Add("system", "Desktop, Unity, Web, Mobile clients talk to AI through the ASP.NET API.");
    }

    public string Id { get; }

    public string Title { get; }

    public DateTimeOffset CreatedAt { get; }

    public IReadOnlyList<ChatMessage> Messages => messages;

    public void Add(string role, string content)
    {
        messages.Add(new ChatMessage(role, content, DateTimeOffset.Now));
    }
}

public sealed record ChatMessage(string Role, string Content, DateTimeOffset CreatedAt);
