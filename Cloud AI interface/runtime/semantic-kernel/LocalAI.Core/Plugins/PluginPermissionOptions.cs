namespace LocalAI.Core.Plugins;

public sealed class PluginPermissionOptions
{
    public string WorkspaceRoot { get; init; } = Directory.GetCurrentDirectory();
    public string NasRootPath { get; init; } = string.Empty;
    public bool AllowFileDelete { get; init; }
    public bool AllowCommandExecution { get; init; }
    public bool AllowNasControl { get; init; }
    public IReadOnlySet<string> AllowedCommands { get; init; } = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
}
