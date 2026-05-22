namespace LocalAI.CloudInterface;

public interface ISharedContextLoader
{
    RuntimeContext Load(CloudAIRequest request);
}
