namespace LocalAI.Core.Security;

public sealed class PluginSecurityOptions
{
    public bool RequireConfirmationForSensitiveFunctions { get; init; } = true;
    public bool LogFunctionCalls { get; init; } = true;
    public IReadOnlySet<string> SensitiveFunctions { get; init; } = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "file.DeleteFile",
        "command.RunAsync",
        "nas.RequireControlPermission",
    };
}
