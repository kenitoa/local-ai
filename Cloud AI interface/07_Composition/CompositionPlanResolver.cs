namespace LocalAI.CloudInterface;

public sealed class CompositionPlanResolver
{
    public ExecutionPlan CreatePlan(CompositionProfile profile, IReadOnlyList<IExpert> experts)
    {
        ArgumentNullException.ThrowIfNull(profile);
        ArgumentNullException.ThrowIfNull(experts);

        var expertsById = experts.ToDictionary(expert => expert.Id, StringComparer.OrdinalIgnoreCase);
        var steps = profile.Strategy switch
        {
            CompositionStrategy.Single => CreateSingleSteps(profile, expertsById),
            CompositionStrategy.Pipeline => CreatePipelineSteps(profile, expertsById),
            CompositionStrategy.ParallelVote => CreateParallelSteps(profile, expertsById, "vote"),
            CompositionStrategy.ParallelJudge => CreateParallelJudgeSteps(profile, expertsById),
            CompositionStrategy.FallbackChain => CreateFallbackSteps(profile, expertsById),
            _ => throw new ArgumentOutOfRangeException(nameof(profile), profile.Strategy, "Unknown composition strategy.")
        };

        return new ExecutionPlan
        {
            Steps = steps,
            RequiresJudge = profile.RequiresJudge || profile.Strategy == CompositionStrategy.ParallelJudge,
            RunInParallel = profile.RunInParallel,
            Metadata = new Dictionary<string, object>
            {
                ["compositionId"] = profile.CompositionId,
                ["strategy"] = profile.Strategy,
                ["fallbackCount"] = profile.Fallback.Count,
                ["fallback"] = profile.Fallback
            }
        };
    }

    private static List<ExecutionStep> CreateSingleSteps(
        CompositionProfile profile,
        IReadOnlyDictionary<string, IExpert> expertsById)
    {
        var expertId = profile.Experts.FirstOrDefault(id => expertsById.ContainsKey(id))
            ?? profile.Fallback.FirstOrDefault(id => expertsById.ContainsKey(id));

        return expertId is null
            ? new List<ExecutionStep>()
            : [CreateStep(1, expertId, "single", "run one selected expert", false, [])];
    }

    private static List<ExecutionStep> CreatePipelineSteps(
        CompositionProfile profile,
        IReadOnlyDictionary<string, IExpert> expertsById)
    {
        var orderedExpertIds = profile.Experts.Where(expertsById.ContainsKey).ToArray();
        var steps = new List<ExecutionStep>();

        for (var i = 0; i < orderedExpertIds.Length; i++)
        {
            steps.Add(CreateStep(
                i + 1,
                orderedExpertIds[i],
                "pipeline",
                "pass previous output to next expert",
                false,
                i == 0 ? [] : [orderedExpertIds[i - 1]]));
        }

        return steps;
    }

    private static List<ExecutionStep> CreateParallelSteps(
        CompositionProfile profile,
        IReadOnlyDictionary<string, IExpert> expertsById,
        string role)
    {
        var workerSteps = profile.Experts
            .Where(expertsById.ContainsKey)
            .Select((expertId, index) => CreateStep(index + 1, expertId, role, "run with peer experts", true, []))
            .ToList();

        if (!profile.RequiresJudge)
        {
            return workerSteps;
        }

        var workerExpertIds = workerSteps.Select(step => step.ExpertId).ToArray();
        var judgeId = profile.Experts.Concat(profile.Fallback).FirstOrDefault(id =>
            expertsById.ContainsKey(id)
            && !workerExpertIds.Contains(id, StringComparer.OrdinalIgnoreCase)
            && IsJudge(expertsById[id]));

        if (judgeId is not null)
        {
            workerSteps.Add(CreateStep(
                workerSteps.Count + 1,
                judgeId,
                "judge",
                "evaluate parallel expert outputs",
                false,
                workerExpertIds));
        }

        return workerSteps;
    }

    private static List<ExecutionStep> CreateParallelJudgeSteps(
        CompositionProfile profile,
        IReadOnlyDictionary<string, IExpert> expertsById)
    {
        var selectedExperts = profile.Experts.Where(expertsById.ContainsKey).ToArray();
        var judgeId = selectedExperts.FirstOrDefault(id =>
            expertsById[id].Profile.ModelType.Equals("judge", StringComparison.OrdinalIgnoreCase)
            || expertsById[id].Profile.Capabilities.Any(capability => capability.Equals("judge", StringComparison.OrdinalIgnoreCase)));

        var workerExpertIds = selectedExperts.Where(id => !string.Equals(id, judgeId, StringComparison.OrdinalIgnoreCase)).ToArray();
        var steps = workerExpertIds
            .Select((expertId, index) => CreateStep(index + 1, expertId, "parallel", "run with peer experts before judge", true, []))
            .ToList();

        if (judgeId is not null)
        {
            steps.Add(CreateStep(steps.Count + 1, judgeId, "judge", "evaluate parallel expert outputs", false, workerExpertIds));
        }

        return steps;
    }

    private static List<ExecutionStep> CreateFallbackSteps(
        CompositionProfile profile,
        IReadOnlyDictionary<string, IExpert> expertsById)
    {
        var expertIds = profile.Experts.Concat(profile.Fallback).Where(expertsById.ContainsKey).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        return expertIds
            .Select((expertId, index) => CreateStep(
                index + 1,
                expertId,
                "fallback",
                "run only if previous expert fails",
                false,
                index == 0 ? [] : [expertIds[index - 1]]))
            .ToList();
    }

    private static ExecutionStep CreateStep(
        int order,
        string expertId,
        string role,
        string reason,
        bool canRunInParallel,
        IReadOnlyList<string> dependsOnExpertIds)
    {
        return new ExecutionStep
        {
            Order = order,
            ExpertId = expertId,
            Role = role,
            Reason = reason,
            CanRunInParallel = canRunInParallel,
            DependsOnExpertIds = dependsOnExpertIds
        };
    }

    private static bool IsJudge(IExpert expert)
    {
        return expert.Profile.ModelType.Equals("judge", StringComparison.OrdinalIgnoreCase)
            || expert.Profile.Capabilities.Any(capability => capability.Equals("judge", StringComparison.OrdinalIgnoreCase));
    }
}
