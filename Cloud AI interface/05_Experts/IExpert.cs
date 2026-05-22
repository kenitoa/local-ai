namespace LocalAI.CloudInterface;

public interface IExpert
{
    string Id { get; }
    ExpertProfile Profile { get; }

    Task<ExpertResult> InvokeAsync(ExpertRequest request);
}
