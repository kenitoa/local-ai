namespace LocalAI.CloudInterface;

public static class MvpReadinessValidator
{
    public static MvpReadinessReport CreateReport()
    {
        return new MvpReadinessReport
        {
            Features =
            [
                Feature(1, "G(x) API", true, nameof(CloudAIService)),
                Feature(1, "Expert interface", true, nameof(IExpert)),
                Feature(1, "Ollama adapter", true, nameof(OllamaExpert)),
                Feature(1, "ML.NET adapter", true, nameof(MLNetExpert)),
                Feature(1, "JSON registry", true, nameof(JsonExpertRegistryLoader)),
                Feature(1, "Rule-based router", true, nameof(RuleBasedRouter)),
                Feature(1, "Single / pipeline execution", true, nameof(CompositionPlanResolver)),

                Feature(2, "Parallel execution", true, nameof(ParallelExecutionEngine)),
                Feature(2, "Aggregator", true, nameof(ScoreBasedAggregator)),
                Feature(2, "Judge model", true, nameof(RuleBasedVerifier)),
                Feature(2, "Trace logging", true, nameof(TraceRecorder)),
                Feature(2, "Fallback chain", true, nameof(RuleBasedRecoveryPolicy)),

                Feature(3, "Dynamic attach/detach", true, nameof(InMemoryExpertLifecycleManager)),
                Feature(3, "Health check", true, nameof(ExpertHealth)),
                Feature(3, "Model lifecycle manager", true, nameof(IExpertLifecycleManager)),
                Feature(3, "Shared memory", true, nameof(RuntimeContext)),
                Feature(3, "Vector memory", true, nameof(VectorMemoryItem)),

                Feature(4, "Scoring router", true, nameof(ScoringRouter)),
                Feature(4, "Composition profile", true, nameof(CompositionProfile)),
                Feature(4, "Self-optimization", true, nameof(SelfOptimizer)),
                Feature(4, "Dashboard", false, "No dashboard UI/API has been implemented in this folder."),

                Feature(5, "Distributed execution", false, "Not implemented."),
                Feature(5, "Multi-node expert hosting", false, "Not implemented."),
                Feature(5, "Load balancing", false, "Not implemented."),
                Feature(5, "Autoscaling", false, "Not implemented."),
                Feature(5, "Permission system", true, nameof(ExpertPermissions))
            ]
        };
    }

    private static MvpFeatureStatus Feature(int level, string name, bool implemented, string evidence)
    {
        return new MvpFeatureStatus
        {
            MvpLevel = level,
            Feature = name,
            Implemented = implemented,
            Evidence = evidence
        };
    }
}
