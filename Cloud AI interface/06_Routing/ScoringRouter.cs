namespace LocalAI.CloudInterface;

public sealed class ScoringRouter : IRouter
{
    private readonly ExpertScorer scorer;

    public ScoringRouter(ExpertScorer? scorer = null)
    {
        this.scorer = scorer ?? new ExpertScorer();
    }

    public Task<ExecutionPlan> CreatePlanAsync(
        CloudAIRequest request,
        RuntimeContext context,
        IReadOnlyList<IExpert> experts)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(experts);

        var requiredCapabilities = DetectCapabilities(request).ToArray();
        var candidates = FilterCandidates(experts, request.Options).ToArray();
        var selected = new List<(IExpert Expert, string Capability, ExpertScore Score)>();

        foreach (var capability in requiredCapabilities)
        {
            var selectedIds = selected.Select(item => item.Expert.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
            var best = candidates
                .Where(expert => !selectedIds.Contains(expert.Id))
                .Select(expert => (Expert: expert, Capability: capability, Score: scorer.Score(expert, request, capability)))
                .OrderByDescending(item => item.Score.TotalScore)
                .ThenBy(expert => expert.Expert.Profile.Priority)
                .FirstOrDefault();

            if (best.Expert is not null)
            {
                selected.Add(best);
            }
        }

        selected = ApplyMaxExperts(selected, request.Options).ToList();
        var steps = selected.Select((item, index) => CreateStep(item, index, selected)).ToList();
        var plan = new ExecutionPlan
        {
            Steps = steps,
            RequiresJudge = steps.Any(step => step.Role.Contains("judge", StringComparison.OrdinalIgnoreCase)),
            RunInParallel = steps.Count(step => step.CanRunInParallel) > 1,
            Metadata = new Dictionary<string, object>
            {
                ["router"] = nameof(ScoringRouter),
                ["capabilities"] = requiredCapabilities,
                ["scores"] = selected.Select(item => item.Score).ToArray(),
                ["sessionId"] = context.SessionId
            }
        };

        context.ExecutionHistory.Add(new ExecutionHistoryEntry
        {
            Step = "Router.ScorePlan",
            Actor = nameof(ScoringRouter),
            InputSummary = request.Input,
            OutputSummary = string.Join(" -> ", steps.Select(step => step.ExpertId)),
            Succeeded = steps.Count > 0,
            Metadata = new Dictionary<string, object>
            {
                ["planId"] = plan.PlanId,
                ["selectedScores"] = selected.ToDictionary(item => item.Expert.Id, item => item.Score.TotalScore)
            }
        });

        return Task.FromResult(plan);
    }

    private static IEnumerable<IExpert> FilterCandidates(IEnumerable<IExpert> experts, RuntimeOptions options)
    {
        var excluded = new HashSet<string>(options.ExcludedExperts, StringComparer.OrdinalIgnoreCase);
        var preferred = new HashSet<string>(options.PreferredExperts, StringComparer.OrdinalIgnoreCase);

        return experts
            .Where(expert => !excluded.Contains(expert.Id))
            .Where(expert => options.AllowExternalApis || !IsExternalProvider(expert.Profile.Provider))
            .OrderByDescending(expert => preferred.Contains(expert.Id));
    }

    private static IEnumerable<string> DetectCapabilities(CloudAIRequest request)
    {
        var taskType = request.TaskType?.Trim().ToLowerInvariant();
        var input = request.Input.ToLowerInvariant();

        if (taskType is "code" || ContainsAny(input, "코드", "최적화", "버그", "refactor", "optimize", "bug", "code"))
        {
            yield return "code";
            yield return "reasoning";
            if (request.Options.RequireVerification)
            {
                yield return "judge";
            }

            yield break;
        }

        if (taskType is "classify" or "classification" || ContainsAny(input, "분류", "classify", "classification", "intent"))
        {
            yield return "intent-classification";
            yield break;
        }

        if (taskType is "vision" || ContainsAny(input, "이미지", "사진", "화면", "image", "vision", "screenshot"))
        {
            yield return "vision";
            yield break;
        }

        if (taskType is "search" || ContainsAny(input, "검색", "찾아", "search", "retrieve"))
        {
            yield return "search";
            yield break;
        }

        if (taskType is "planning" or "plan" || ContainsAny(input, "계획", "설계", "plan", "planning"))
        {
            yield return "planning";
            yield break;
        }

        yield return "chat";
    }

    private static IEnumerable<(IExpert Expert, string Capability, ExpertScore Score)> ApplyMaxExperts(
        IReadOnlyList<(IExpert Expert, string Capability, ExpertScore Score)> selected,
        RuntimeOptions options)
    {
        if (options.MaxExperts <= 0 || selected.Count <= options.MaxExperts)
        {
            return selected;
        }

        var judges = selected.Where(item => item.Capability.Equals("judge", StringComparison.OrdinalIgnoreCase)).ToArray();
        var nonJudges = selected.Where(item => !item.Capability.Equals("judge", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(item => item.Score.TotalScore)
            .Take(Math.Max(0, options.MaxExperts - judges.Length));

        return nonJudges.Concat(judges).Take(options.MaxExperts);
    }

    private static ExecutionStep CreateStep(
        (IExpert Expert, string Capability, ExpertScore Score) item,
        int index,
        IReadOnlyList<(IExpert Expert, string Capability, ExpertScore Score)> selected)
    {
        var isJudge = item.Capability.Equals("judge", StringComparison.OrdinalIgnoreCase);
        var dependencyIds = isJudge
            ? selected.Where(other => !other.Capability.Equals("judge", StringComparison.OrdinalIgnoreCase)).Select(other => other.Expert.Id).ToArray()
            : Array.Empty<string>();

        return new ExecutionStep
        {
            Order = index + 1,
            ExpertId = item.Expert.Id,
            Role = $"{item.Capability}-expert",
            Reason = $"score={item.Score.TotalScore:0.###}",
            CanRunInParallel = !isJudge,
            DependsOnExpertIds = dependencyIds,
            Metadata = new Dictionary<string, object>
            {
                ["score"] = item.Score.TotalScore,
                ["capabilityMatch"] = item.Score.CapabilityMatch,
                ["qualityScore"] = item.Score.QualityScore,
                ["successRate"] = item.Score.SuccessRate,
                ["latencyPenalty"] = item.Score.LatencyPenalty,
                ["costPenalty"] = item.Score.CostPenalty,
                ["memoryPenalty"] = item.Score.MemoryPenalty
            }
        };
    }

    private static bool IsExternalProvider(string provider)
    {
        return provider.Contains("openai", StringComparison.OrdinalIgnoreCase)
            || provider.Contains("external", StringComparison.OrdinalIgnoreCase)
            || provider.Contains("api", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ContainsAny(string input, params string[] needles)
    {
        return needles.Any(needle => input.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }
}
