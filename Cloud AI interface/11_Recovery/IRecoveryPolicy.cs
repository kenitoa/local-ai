namespace LocalAI.CloudInterface;

public interface IRecoveryPolicy
{
    Task<RecoveryDecision> CreateRecoveryAsync(RecoveryInput input);
}
