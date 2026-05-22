namespace LocalAI.CloudInterface;

public interface IMemoryUpdater
{
    Task UpdateAsync(
        CloudAIRequest request,
        CloudAIResponse response,
        RequestTrace trace,
        RuntimeContext context);
}
