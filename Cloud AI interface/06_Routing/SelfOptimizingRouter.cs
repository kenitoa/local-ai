namespace LocalAI.CloudInterface;

public sealed class SelfOptimizingRouter : IRouter
{
    private readonly ISelfOptimizer optimizer;
    private readonly ICompositionProfileRegistry compositionRegistry;
    private readonly CompositionPlanResolver resolver;
    private readonly IRouter fallbackRouter;

    public SelfOptimizingRouter(
        ISelfOptimizer optimizer,
        ICompositionProfileRegistry compositionRegistry,
        CompositionPlanResolver? resolver = null,
        IRouter? fallbackRouter = null)
    {
        this.optimizer = optimizer;
        this.compositionRegistry = compositionRegistry;
        this.resolver = resolver ?? new CompositionPlanResolver();
        this.fallbackRouter = fallbackRouter ?? new ScoringRouter();
    }

    public async Task<ExecutionPlan> CreatePlanAsync(
        CloudAIRequest request,
        RuntimeContext context,
        IReadOnlyList<IExpert> experts)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(experts);

        var recommendation = await optimizer.RecommendAsync(request).ConfigureAwait(false);
        if (!string.IsNullOrWhiteSpace(recommendation.CompositionId))
        {
            var profile = await compositionRegistry.GetAsync(recommendation.CompositionId).ConfigureAwait(false);
            if (profile is not null)
            {
                var plan = resolver.CreatePlan(profile, experts);
                plan.Metadata["router"] = nameof(SelfOptimizingRouter);
                plan.Metadata["optimizationScore"] = recommendation.Score;
                plan.Metadata["optimizationReason"] = recommendation.Reason;
                plan.Metadata["inputType"] = recommendation.InputType;

                context.ExecutionHistory.Add(new ExecutionHistoryEntry
                {
                    Step = "Router.SelfOptimize",
                    Actor = nameof(SelfOptimizingRouter),
                    InputSummary = request.Input,
                    OutputSummary = string.Join(" -> ", plan.Steps.Select(step => step.ExpertId)),
                    Succeeded = plan.Steps.Count > 0,
                    Metadata = new Dictionary<string, object>
                    {
                        ["compositionId"] = recommendation.CompositionId,
                        ["score"] = recommendation.Score,
                        ["reason"] = recommendation.Reason
                    }
                });

                return plan;
            }
        }

        return await fallbackRouter.CreatePlanAsync(request, context, experts).ConfigureAwait(false);
    }
}
