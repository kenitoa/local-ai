namespace LocalAI.CloudInterface;

public sealed class CompositionProfileRouter : IRouter
{
    private readonly ICompositionProfileRegistry profileRegistry;
    private readonly CompositionPlanResolver resolver;
    private readonly IRouter fallbackRouter;

    public CompositionProfileRouter(
        ICompositionProfileRegistry profileRegistry,
        CompositionPlanResolver? resolver = null,
        IRouter? fallbackRouter = null)
    {
        this.profileRegistry = profileRegistry;
        this.resolver = resolver ?? new CompositionPlanResolver();
        this.fallbackRouter = fallbackRouter ?? new RuleBasedRouter();
    }

    public async Task<ExecutionPlan> CreatePlanAsync(
        CloudAIRequest request,
        RuntimeContext context,
        IReadOnlyList<IExpert> experts)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(experts);

        var profile = await SelectProfileAsync(request, experts).ConfigureAwait(false);
        if (profile is null)
        {
            return await fallbackRouter.CreatePlanAsync(request, context, experts).ConfigureAwait(false);
        }

        var plan = resolver.CreatePlan(profile, experts);
        context.ExecutionHistory.Add(new ExecutionHistoryEntry
        {
            Step = "Router.CreateCompositionPlan",
            Actor = nameof(CompositionProfileRouter),
            InputSummary = request.Input,
            OutputSummary = string.Join(" -> ", plan.Steps.Select(step => step.ExpertId)),
            Succeeded = plan.Steps.Count > 0,
            Metadata = new Dictionary<string, object>
            {
                ["planId"] = plan.PlanId,
                ["compositionId"] = profile.CompositionId,
                ["strategy"] = profile.Strategy
            }
        });

        return plan;
    }

    private async Task<CompositionProfile?> SelectProfileAsync(
        CloudAIRequest request,
        IReadOnlyList<IExpert> experts)
    {
        if (!string.IsNullOrWhiteSpace(request.Options.CompositionId))
        {
            return await profileRegistry.GetAsync(request.Options.CompositionId).ConfigureAwait(false);
        }

        var profiles = await profileRegistry.GetAllAsync().ConfigureAwait(false);
        if (profiles.Count == 0)
        {
            return null;
        }

        var defaultCompositionId = DetectDefaultCompositionId(request);
        var expertIds = experts.Select(expert => expert.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);

        return profiles
            .Where(profile => IsExecutable(profile, expertIds))
            .OrderByDescending(profile => string.Equals(profile.CompositionId, defaultCompositionId, StringComparison.OrdinalIgnoreCase))
            .ThenBy(profile => ProfilePriority(profile, request))
            .ThenBy(profile => profile.CompositionId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
    }

    private static bool IsExecutable(CompositionProfile profile, IReadOnlySet<string> expertIds)
    {
        return profile.Experts.Concat(profile.Fallback)
            .Any(expertId => expertIds.Contains(expertId));
    }

    private static int ProfilePriority(CompositionProfile profile, CloudAIRequest request)
    {
        var taskType = request.TaskType?.Trim().ToLowerInvariant();
        var input = request.Input.ToLowerInvariant();

        if (taskType is "code" || ContainsAny(input, "code", "bug", "optimize", "refactor"))
        {
            return profile.CompositionId.Contains("code", StringComparison.OrdinalIgnoreCase) ? 0 : 10;
        }

        if (taskType is "classify" or "classification" || ContainsAny(input, "classify", "classification", "intent"))
        {
            return profile.CompositionId.Contains("classify", StringComparison.OrdinalIgnoreCase) ? 0 : 10;
        }

        if (taskType is "planning" or "plan" || ContainsAny(input, "plan", "planning", "reason"))
        {
            return profile.CompositionId.Contains("reasoning", StringComparison.OrdinalIgnoreCase) ? 0 : 10;
        }

        return profile.CompositionId.Contains("chat", StringComparison.OrdinalIgnoreCase) ? 0 : 10;
    }

    private static string DetectDefaultCompositionId(CloudAIRequest request)
    {
        var taskType = request.TaskType?.Trim().ToLowerInvariant();
        var input = request.Input.ToLowerInvariant();

        if (taskType is "code" || ContainsAny(input, "code", "bug", "optimize", "refactor"))
        {
            return "code-pipeline-v1";
        }

        if (taskType is "classify" or "classification" || ContainsAny(input, "classify", "classification", "intent"))
        {
            return "fallback-classify-v1";
        }

        if (taskType is "planning" or "plan" || ContainsAny(input, "plan", "planning", "reason"))
        {
            return "korean-reasoning-v1";
        }

        return "general-chat-v1";
    }

    private static bool ContainsAny(string input, params string[] needles)
    {
        return needles.Any(needle => input.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }
}
