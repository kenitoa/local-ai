using LocalAI.CloudInterface;

namespace AspNetAiApi;

public sealed class ChatService(
    SessionStore sessions,
    ICloudAI cloudAi)
{
    public async Task<ChatResponse> SendAsync(ChatRequest request, CancellationToken cancellationToken)
    {
        var session = sessions.GetOrCreate(request.SessionId);
        var model = string.IsNullOrWhiteSpace(request.Model) ? "llama3.2" : request.Model.Trim();
        var preferredExperts = NormalizePreferredExperts(request);
        var message = string.IsNullOrWhiteSpace(request.Message)
            ? "API connection check message."
            : request.Message.Trim();

        session.Add("user", message);

        cancellationToken.ThrowIfCancellationRequested();
        var result = await cloudAi.InvokeAsync(new CloudAIRequest
        {
            RequestId = Guid.NewGuid().ToString("N"),
            UserId = "ui-api",
            Input = message,
            TaskType = "chat",
            SharedContext = new RuntimeContext { SessionId = session.Id },
            Options = new RuntimeOptions
            {
                CompositionId = string.IsNullOrWhiteSpace(request.CompositionId)
                    ? null
                    : request.CompositionId.Trim(),
                PreferredExperts = preferredExperts,
                RequireVerification = true
            }
        });

        session.Add("assistant", result.Output);

        return new ChatResponse(
            session.Id,
            model,
            result.Output,
            "cloud-ai-interface",
            session.Messages.Select(FromMessage).ToList());
    }

    public async IAsyncEnumerable<string> StreamAsync(
        ChatRequest request,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var response = await SendAsync(request, cancellationToken);
        var words = response.Response.Split(' ', StringSplitOptions.RemoveEmptyEntries);

        foreach (var word in words)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return word;
            await Task.Delay(60, cancellationToken);
        }
    }

    private static ChatMessageDto FromMessage(ChatMessage message)
    {
        return new ChatMessageDto(message.Role, message.Content, message.CreatedAt);
    }

    private static IReadOnlyList<string> NormalizePreferredExperts(ChatRequest request)
    {
        var explicitExperts = request.PreferredExperts?
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        if (explicitExperts is { Length: > 0 })
        {
            return explicitExperts;
        }

        var model = string.IsNullOrWhiteSpace(request.Model) ? "llama3.2" : request.Model.Trim();
        return [ToOllamaExpertId(model)];
    }

    private static string ToOllamaExpertId(string model)
    {
        var normalized = model.ToLowerInvariant()
            .Select(ch => char.IsLetterOrDigit(ch) ? ch : '-')
            .ToArray();
        var id = new string(normalized).Trim('-');

        while (id.Contains("--", StringComparison.Ordinal))
        {
            id = id.Replace("--", "-", StringComparison.Ordinal);
        }

        if (!id.EndsWith("-latest", StringComparison.OrdinalIgnoreCase) && !model.Contains(':', StringComparison.Ordinal))
        {
            id += "-latest";
        }

        return $"ollama-{id}";
    }
}
