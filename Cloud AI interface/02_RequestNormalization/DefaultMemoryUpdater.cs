namespace LocalAI.CloudInterface;

public sealed class DefaultMemoryUpdater : IMemoryUpdater
{
    public Task UpdateAsync(
        CloudAIRequest request,
        CloudAIResponse response,
        RequestTrace trace,
        RuntimeContext context)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(response);
        ArgumentNullException.ThrowIfNull(trace);
        ArgumentNullException.ThrowIfNull(context);

        lock (context)
        {
            context.WorkingMemory["lastResponse"] = response.Output;
            context.WorkingMemory["lastConfidence"] = response.Confidence;
            context.WorkingMemory["lastTrace"] = trace;
            context.Conversation.Add(new Message
            {
                Role = "assistant",
                Content = response.Output,
                Metadata = new Dictionary<string, object>
                {
                    ["requestId"] = request.RequestId,
                    ["confidence"] = response.Confidence
                }
            });
        }

        return Task.CompletedTask;
    }
}
