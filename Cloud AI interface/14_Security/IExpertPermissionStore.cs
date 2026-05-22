namespace LocalAI.CloudInterface;

public interface IExpertPermissionStore
{
    Task SetAsync(ExpertPermissionPolicy policy);
    Task<ExpertPermissions> GetAsync(string expertId);
}
