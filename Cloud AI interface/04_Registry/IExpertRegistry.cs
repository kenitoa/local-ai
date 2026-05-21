namespace LocalAI.CloudInterface;

public interface IExpertRegistry
{
    Task RegisterAsync(IExpert expert);
    Task UnregisterAsync(string expertId);
    Task<IExpert?> GetAsync(string expertId);
    Task<IReadOnlyList<IExpert>> FindByCapabilityAsync(string capability);
    Task<IReadOnlyList<IExpert>> GetAllAsync();
}
