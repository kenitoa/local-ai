namespace LocalAI.CloudInterface;

public interface IExpertRuntimeLimitProvider
{
    ExpertRuntimeLimit GetLimit(IExpert expert);
}
