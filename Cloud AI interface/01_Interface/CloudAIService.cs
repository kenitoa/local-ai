namespace LocalAI.CloudInterface;

public sealed class CloudAIService : ICloudAI
{
    private readonly ICloudAIRequestNormalizer requestNormalizer;
    private readonly ISharedContextLoader sharedContextLoader;
    private readonly IExpertRegistry expertRegistry;
    private readonly IRouter router;
    private readonly IExecutionEngine executionEngine;
    private readonly IAggregator aggregator;
    private readonly IVerifier verifier;
    private readonly IRecoveryPolicy recoveryPolicy;
    private readonly ITraceRecorder traceRecorder;
    private readonly IMemoryUpdater memoryUpdater;
    private readonly ISelfOptimizer? selfOptimizer;

    public CloudAIService(
        ICloudAIRequestNormalizer requestNormalizer,
        ISharedContextLoader sharedContextLoader,
        IExpertRegistry expertRegistry,
        IRouter router,
        IExecutionEngine executionEngine,
        IAggregator aggregator,
        IVerifier verifier,
        IRecoveryPolicy recoveryPolicy,
        ITraceRecorder traceRecorder,
        IMemoryUpdater memoryUpdater,
        ISelfOptimizer? selfOptimizer = null)
    {
        this.requestNormalizer = requestNormalizer;
        this.sharedContextLoader = sharedContextLoader;
        this.expertRegistry = expertRegistry;
        this.router = router;
        this.executionEngine = executionEngine;
        this.aggregator = aggregator;
        this.verifier = verifier;
        this.recoveryPolicy = recoveryPolicy;
        this.traceRecorder = traceRecorder;
        this.memoryUpdater = memoryUpdater;
        this.selfOptimizer = selfOptimizer;
    }

    public async Task<CloudAIResponse> InvokeAsync(CloudAIRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var normalizedRequest = requestNormalizer.Normalize(request);
        var startedAt = DateTimeOffset.UtcNow;
        var context = sharedContextLoader.Load(normalizedRequest);

        var experts = await expertRegistry.GetAllAsync().ConfigureAwait(false);
        var plan = await router.CreatePlanAsync(normalizedRequest, context, experts).ConfigureAwait(false);
        var expertResults = await executionEngine.ExecuteAsync(plan, context).ConfigureAwait(false);
        var aggregated = await aggregator.AggregateAsync(expertResults, context).ConfigureAwait(false);
        var verified = await verifier.VerifyAsync(aggregated, context).ConfigureAwait(false);
        RecoveryDecision? recoveryDecision = null;

        if (verified.NeedsRetry)
        {
            recoveryDecision = await recoveryPolicy.CreateRecoveryAsync(new RecoveryInput
            {
                Request = normalizedRequest,
                Plan = plan,
                ExpertResults = expertResults,
                AggregatedResult = aggregated,
                VerifiedResult = verified,
                AvailableExperts = experts,
                Context = context
            }).ConfigureAwait(false);

            if (recoveryDecision.ShouldRecover && recoveryDecision.RetryPlan is not null)
            {
                if (recoveryDecision.Delay > TimeSpan.Zero)
                {
                    await Task.Delay(recoveryDecision.Delay).ConfigureAwait(false);
                }

                var retryResults = await executionEngine.ExecuteAsync(recoveryDecision.RetryPlan, context).ConfigureAwait(false);
                expertResults = expertResults.Concat(retryResults).ToArray();
                aggregated = await aggregator.AggregateAsync(expertResults, context).ConfigureAwait(false);
                verified = await verifier.VerifyAsync(aggregated, context).ConfigureAwait(false);
            }
        }

        var completedAt = DateTimeOffset.UtcNow;
        var trace = await traceRecorder.RecordAsync(new TraceRecordInput
        {
            Request = normalizedRequest,
            Plan = plan,
            ExpertResults = expertResults,
            AggregatedResult = aggregated,
            VerifiedResult = verified,
            RecoveryDecision = recoveryDecision,
            Context = context,
            StartedAt = startedAt,
            CompletedAt = completedAt
        }).ConfigureAwait(false);

        if (selfOptimizer is not null)
        {
            await selfOptimizer.RecordAsync(trace).ConfigureAwait(false);
        }

        var response = CloudAIResponseFactory.FromVerifiedResult(verified, aggregated, context);
        await memoryUpdater.UpdateAsync(normalizedRequest, response, trace, context).ConfigureAwait(false);
        return response;
    }
}
