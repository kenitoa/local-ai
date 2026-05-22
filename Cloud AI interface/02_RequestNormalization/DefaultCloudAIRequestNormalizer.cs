namespace LocalAI.CloudInterface;

public sealed class DefaultCloudAIRequestNormalizer : ICloudAIRequestNormalizer
{
    public CloudAIRequest Normalize(CloudAIRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var requestId = string.IsNullOrWhiteSpace(request.RequestId)
            ? Guid.NewGuid().ToString("N")
            : request.RequestId.Trim();
        var userId = string.IsNullOrWhiteSpace(request.UserId)
            ? "anonymous"
            : request.UserId.Trim();
        var input = request.Input?.Trim() ?? string.Empty;
        var taskType = string.IsNullOrWhiteSpace(request.TaskType)
            ? null
            : request.TaskType.Trim().ToLowerInvariant();

        return new CloudAIRequest
        {
            RequestId = requestId,
            UserId = userId,
            Input = input,
            TaskType = taskType,
            Context = request.Context,
            SharedContext = request.SharedContext,
            Options = request.Options
        };
    }
}
