namespace LocalAI.CloudInterface;

public interface IOptimizationStore
{
    Task AddAsync(OptimizationRecord record);
    Task<IReadOnlyList<OptimizationRecord>> GetByInputTypeAsync(string inputType);
    Task<IReadOnlyList<CompositionPerformanceStats>> GetStatsAsync(string inputType);
}
