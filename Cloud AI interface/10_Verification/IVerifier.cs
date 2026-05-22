namespace LocalAI.CloudInterface;

public interface IVerifier
{
    Task<VerifiedResult> VerifyAsync(
        AggregatedResult result,
        RuntimeContext context);
}
