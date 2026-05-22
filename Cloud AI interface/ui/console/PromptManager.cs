namespace ConsoleValidation;

public sealed class PromptManager
{
    public string SystemPrompt =>
        "You are the first-pass console validator. Answer briefly and report connection errors plainly.";

    public string BuildUserPrompt(string userMessage)
    {
        return $"""
        {SystemPrompt}

        User request:
        {userMessage}
        """;
    }
}
