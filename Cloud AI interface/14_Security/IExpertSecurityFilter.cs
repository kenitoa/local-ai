namespace LocalAI.CloudInterface;

public interface IExpertSecurityFilter
{
    Task<SecurityFilterResult> FilterRequestAsync(
        IExpert expert,
        ExpertRequest request,
        ExpertPermissions permissions);

    Task<ExpertResult> FilterResultAsync(
        IExpert expert,
        ExpertResult result,
        ExpertPermissions permissions);
}
