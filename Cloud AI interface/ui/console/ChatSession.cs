namespace ConsoleValidation;

public sealed class ChatSession
{
    private readonly List<ChatMessage> messages = new();

    public IReadOnlyList<ChatMessage> Messages => messages;

    public void Add(string role, string content)
    {
        messages.Add(new ChatMessage(role, content, DateTimeOffset.Now));
    }
}

public sealed record ChatMessage(string Role, string Content, DateTimeOffset CreatedAt);
