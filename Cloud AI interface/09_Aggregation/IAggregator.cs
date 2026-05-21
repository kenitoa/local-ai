namespace LocalAI.CloudInterface;

public interface IAggregator
{
    Task<AggregatedResult> AggregateAsync(
        IReadOnlyList<ExpertResult> results,
        RuntimeContext context);
}
