namespace LocalAI.CloudInterface;

public sealed class DefaultSharedContextLoader : ISharedContextLoader
{
    public RuntimeContext Load(CloudAIRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var context = request.SharedContext;

        lock (context)
        {
            context.WorkingMemory["requestId"] = request.RequestId;
            context.WorkingMemory["input"] = request.Input;
            context.WorkingMemory["runtimeOptions"] = request.Options;

            if (!string.IsNullOrWhiteSpace(request.TaskType))
            {
                context.WorkingMemory["taskType"] = request.TaskType;
            }

            foreach (var item in request.Context)
            {
                context.WorkingMemory[item.Key] = item.Value;
            }

            context.UserMemory["userId"] = request.UserId;
            context.Conversation.Add(new Message
            {
                Role = "user",
                Content = request.Input,
                Metadata = new Dictionary<string, object>
                {
                    ["requestId"] = request.RequestId
                }
            });
        }

        return context;
    }
}
