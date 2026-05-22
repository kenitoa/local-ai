namespace LocalAI.CloudInterface;

public interface ICompositionProfileRegistry
{
    Task RegisterAsync(CompositionProfile profile);
    Task UnregisterAsync(string compositionId);
    Task<CompositionProfile?> GetAsync(string compositionId);
    Task<IReadOnlyList<CompositionProfile>> GetAllAsync();
    Task<IReadOnlyList<CompositionProfile>> FindByExpertAsync(string expertId);
    Task<IReadOnlyList<CompositionProfile>> FindByStrategyAsync(string strategy);
}
