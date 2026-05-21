namespace LocalAI.CloudInterface;

public sealed class RuleBasedRouter : IRouter
{
    public Task<ExecutionPlan> CreatePlanAsync(
        CloudAIRequest request,
        RuntimeContext context,
        IReadOnlyList<IExpert> experts)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(experts);

        var candidates = FilterCandidates(experts, request.Options).ToArray();
        var intent = DetectIntent(request);
        var steps = intent switch
        {
            RouterIntent.Code => CreateCodePlan(candidates),
            RouterIntent.Classify => CreateSingleCapabilityPlan(candidates, "intent-classification", "classifier", "classify request intent"),
            RouterIntent.Vision => CreateSingleCapabilityPlan(candidates, "vision", "vision", "analyze visual input"),
            RouterIntent.Search => CreateSingleCapabilityPlan(candidates, "search", "search", "retrieve relevant context"),
            RouterIntent.Planning => CreateSingleCapabilityPlan(candidates, "planning", "planner", "create execution plan"),
            RouterIntent.Judge => CreateSingleCapabilityPlan(candidates, "judge", "judge", "verify or compare result"),
            _ => CreateGeneralChatPlan(candidates)
        };

        steps = ApplyMaxExperts(steps, request.Options).ToList();
        var requiresJudge = request.Options.RequireVerification && steps.Any(step => IsJudgeRole(step.Role));

        var plan = new ExecutionPlan
        {
            Steps = steps,
            RequiresJudge = requiresJudge,
            RunInParallel = CanRunInParallel(steps),
            Metadata = new Dictionary<string, object>
            {
                ["intent"] = intent.ToString(),
                ["candidateCount"] = candidates.Length,
                ["sessionId"] = context.SessionId
            }
        };

        context.ExecutionHistory.Add(new ExecutionHistoryEntry
        {
            Step = "Router.CreatePlan",
            Actor = nameof(RuleBasedRouter),
            InputSummary = request.Input,
            OutputSummary = string.Join(" -> ", plan.Steps.Select(step => step.ExpertId)),
            Succeeded = plan.Steps.Count > 0,
            Metadata = new Dictionary<string, object>
            {
                ["planId"] = plan.PlanId,
                ["intent"] = intent.ToString(),
                ["requiresJudge"] = plan.RequiresJudge
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
            .OrderByDescending(expert => preferred.Contains(expert.Id))
            .ThenBy(expert => expert.Profile.Priority)
            .ThenByDescending(expert => expert.Profile.QualityScore)
            .ThenByDescending(expert => expert.Profile.LatencyScore)
            .ThenBy(expert => expert.Id, StringComparer.OrdinalIgnoreCase);
    }

    private static List<ExecutionStep> CreateCodePlan(IReadOnlyList<IExpert> experts)
    {
        var selected = new List<(IExpert Expert, string Role, string Reason)>();

        AddIfFound(selected, experts, "code", "code-expert", "handle source code changes or analysis");
        AddIfFound(selected, experts, "reasoning", "reasoning-expert", "reason about the implementation path");
        AddIfFound(selected, experts, "judge", "judge-expert", "compare and verify candidate results");

        return ToSteps(selected, parallelUntilJudge: true);
    }

    private static List<ExecutionStep> CreateSingleCapabilityPlan(
        IReadOnlyList<IExpert> experts,
        string capability,
        string role,
        string reason)
    {
        var selected = SelectByCapability(experts, capability)
            ?? SelectByModelType(experts, capability)
            ?? SelectGeneralLlm(experts);

        return selected is null
            ? new List<ExecutionStep>()
            : ToSteps([(selected, role, reason)], parallelUntilJudge: false);
    }

    private static List<ExecutionStep> CreateGeneralChatPlan(IReadOnlyList<IExpert> experts)
    {
        var selected = SelectByCapability(experts, "chat")
            ?? SelectByCapability(experts, "korean")
            ?? SelectGeneralLlm(experts);

        return selected is null
            ? new List<ExecutionStep>()
            : ToSteps([(selected, "general-chat", "answer the user request")], parallelUntilJudge: false);
    }

    private static void AddIfFound(
        List<(IExpert Expert, string Role, string Reason)> selected,
        IReadOnlyList<IExpert> experts,
        string capability,
        string role,
        string reason)
    {
        var selectedIds = selected.Select(item => item.Expert.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var expert = SelectByCapability(experts, capability, selectedIds)
            ?? (capability == "judge" ? SelectByModelType(experts, "judge", selectedIds) : null)
            ?? (capability is "code" or "reasoning" ? SelectGeneralLlm(experts, selectedIds) : null);

        if (expert is not null && selected.All(item => !string.Equals(item.Expert.Id, expert.Id, StringComparison.OrdinalIgnoreCase)))
        {
            selected.Add((expert, role, reason));
        }
    }

    private static List<ExecutionStep> ToSteps(
        IReadOnlyList<(IExpert Expert, string Role, string Reason)> selected,
        bool parallelUntilJudge)
    {
        var expertIds = selected.Select(item => item.Expert.Id).ToArray();
        var steps = new List<ExecutionStep>();

        for (var i = 0; i < selected.Count; i++)
        {
            var (expert, role, reason) = selected[i];
            var isJudge = IsJudgeRole(role);
            steps.Add(new ExecutionStep
            {
                Order = i + 1,
                ExpertId = expert.Id,
                Role = role,
                Reason = reason,
                CanRunInParallel = parallelUntilJudge && !isJudge,
                DependsOnExpertIds = isJudge ? expertIds.Where(id => !string.Equals(id, expert.Id, StringComparison.OrdinalIgnoreCase)).ToArray() : Array.Empty<string>(),
                Metadata = new Dictionary<string, object>
                {
                    ["provider"] = expert.Profile.Provider,
                    ["modelType"] = expert.Profile.ModelType
                }
            });
        }

        return steps;
    }

    private static IEnumerable<ExecutionStep> ApplyMaxExperts(IEnumerable<ExecutionStep> steps, RuntimeOptions options)
    {
        if (options.MaxExperts <= 0)
        {
            return steps;
        }

        var ordered = steps.OrderBy(step => step.Order).ToList();
        if (ordered.Count <= options.MaxExperts)
        {
            return ordered;
        }

        var judges = ordered.Where(step => IsJudgeRole(step.Role)).ToArray();
        var nonJudges = ordered.Where(step => !IsJudgeRole(step.Role)).Take(Math.Max(0, options.MaxExperts - judges.Length));
        return nonJudges.Concat(judges).Take(options.MaxExperts).Select((step, index) => new ExecutionStep
        {
            Order = index + 1,
            ExpertId = step.ExpertId,
            Role = step.Role,
            Reason = step.Reason,
            CanRunInParallel = step.CanRunInParallel,
            DependsOnExpertIds = step.DependsOnExpertIds,
            Metadata = step.Metadata
        });
    }

    private static RouterIntent DetectIntent(CloudAIRequest request)
    {
        var taskType = request.TaskType?.Trim().ToLowerInvariant();
        var input = request.Input.ToLowerInvariant();

        if (taskType is "code" || ContainsAny(input, "코드", "최적화", "버그", "리팩터", "refactor", "optimize", "bug", "code"))
        {
            return RouterIntent.Code;
        }

        if (taskType is "classify" or "classification" || ContainsAny(input, "분류", "classify", "classification", "intent"))
        {
            return RouterIntent.Classify;
        }

        if (taskType is "vision" || ContainsAny(input, "이미지", "사진", "화면", "image", "vision", "screenshot"))
        {
            return RouterIntent.Vision;
        }

        if (taskType is "search" || ContainsAny(input, "검색", "찾아", "search", "retrieve"))
        {
            return RouterIntent.Search;
        }

        if (taskType is "planning" or "plan" || ContainsAny(input, "계획", "설계", "plan", "planning"))
        {
            return RouterIntent.Planning;
        }

        if (taskType is "judge" || ContainsAny(input, "검증", "비교", "평가", "judge", "verify", "compare"))
        {
            return RouterIntent.Judge;
        }

        return RouterIntent.Chat;
    }

    private static IExpert? SelectByCapability(
        IEnumerable<IExpert> experts,
        string capability,
        IReadOnlySet<string>? excludedExpertIds = null)
    {
        return experts.FirstOrDefault(expert =>
            !(excludedExpertIds?.Contains(expert.Id) ?? false)
            && expert.Profile.Capabilities.Any(candidate =>
                string.Equals(candidate, capability, StringComparison.OrdinalIgnoreCase)));
    }

    private static IExpert? SelectByModelType(
        IEnumerable<IExpert> experts,
        string modelType,
        IReadOnlySet<string>? excludedExpertIds = null)
    {
        return experts.FirstOrDefault(expert =>
            !(excludedExpertIds?.Contains(expert.Id) ?? false)
            &&
            string.Equals(expert.Profile.ModelType, modelType, StringComparison.OrdinalIgnoreCase));
    }

    private static IExpert? SelectGeneralLlm(
        IEnumerable<IExpert> experts,
        IReadOnlySet<string>? excludedExpertIds = null)
    {
        return experts.FirstOrDefault(expert =>
            !(excludedExpertIds?.Contains(expert.Id) ?? false)
            &&
            string.Equals(expert.Profile.ModelType, "llm", StringComparison.OrdinalIgnoreCase));
    }

    private static bool CanRunInParallel(IReadOnlyList<ExecutionStep> steps)
    {
        return steps.Count(step => step.CanRunInParallel) > 1;
    }

    private static bool IsJudgeRole(string role)
    {
        return role.Contains("judge", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsExternalProvider(string provider)
    {
        return provider.Contains("openai", StringComparison.OrdinalIgnoreCase)
            || provider.Contains("external", StringComparison.OrdinalIgnoreCase)
            || provider.Contains("api", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ContainsAny(string input, params string[] needles)
    {
        return needles.Any(input.Contains);
    }

    private enum RouterIntent
    {
        Chat,
        Code,
        Classify,
        Vision,
        Search,
        Planning,
        Judge
    }
}
