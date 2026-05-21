namespace LocalAI.CloudInterface;

public interface ICloudAI
{
    Task<CloudAIResponse> InvokeAsync(CloudAIRequest request);
}
