namespace AspNetAiApi;

public sealed class PromptManager
{
    public string BuildChatPrompt(IReadOnlyList<ChatMessage> messages, string userMessage)
    {
        var recent = messages
            .TakeLast(8)
            .Select(message => $"{message.Role}: {message.Content}");

        return $"""
        You are the ASP.NET API separation layer for a local AI app.
        Answer briefly and report infrastructure failures plainly.

        Conversation:
        {string.Join('\n', recent)}

        Latest user message:
        {userMessage}
        """;
    }
}
