namespace LocalAI.CloudInterface;

public interface ICloudAIRequestNormalizer
{
    CloudAIRequest Normalize(CloudAIRequest request);
}
