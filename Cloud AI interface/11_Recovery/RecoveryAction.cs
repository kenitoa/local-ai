namespace LocalAI.CloudInterface;

public static class RecoveryAction
{
    public const string UseFallbackModel = "use-fallback-model";
    public const string RepairPrompt = "repair-prompt";
    public const string AddExpertAndRetry = "add-expert-and-retry";
    public const string Rejudge = "rejudge";
    public const string UnloadModelAndFallback = "unload-model-and-fallback";
    public const string BackoffAndRetry = "backoff-and-retry";
    public const string Stop = "stop";
}
