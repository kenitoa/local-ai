namespace LocalAI.CloudInterface;

public sealed class RegisteredExpert : ExpertAdapterBase
{
    public RegisteredExpert(ExpertProfile profile, Func<ExpertRequest, Task<ExpertResult>>? invokeAsync = null)
        : base(profile, invokeAsync)
    {
    }
}
