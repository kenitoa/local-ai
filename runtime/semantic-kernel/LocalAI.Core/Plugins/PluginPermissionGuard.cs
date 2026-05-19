namespace LocalAI.Core.Plugins;

public sealed class PluginPermissionGuard
{
    private readonly PluginPermissionOptions _options;

    public PluginPermissionGuard()
        : this(new PluginPermissionOptions())
    {
    }

    public PluginPermissionGuard(PluginPermissionOptions options)
    {
        _options = options;
        WorkspaceRoot = Path.GetFullPath(options.WorkspaceRoot);
    }

    public string WorkspaceRoot { get; }

    public string ResolveWorkspacePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Path cannot be empty.", nameof(path));
        }

        var candidate = Path.IsPathRooted(path)
            ? path
            : Path.Combine(WorkspaceRoot, path);

        var resolved = Path.GetFullPath(candidate);
        if (!IsSameOrChildPath(resolved, WorkspaceRoot))
        {
            throw new UnauthorizedAccessException($"Path is outside the allowed workspace: {path}");
        }

        return resolved;
    }

    public void DemandFileDelete()
    {
        if (!_options.AllowFileDelete)
        {
            throw new UnauthorizedAccessException("File deletion is disabled by plugin permission policy.");
        }
    }

    public void DemandCommandExecution(string command)
    {
        if (!_options.AllowCommandExecution)
        {
            throw new UnauthorizedAccessException("Command execution is disabled by plugin permission policy.");
        }

        if (_options.AllowedCommands.Count > 0 && !_options.AllowedCommands.Contains(command))
        {
            throw new UnauthorizedAccessException($"Command is not allowed by plugin permission policy: {command}");
        }
    }

    public void DemandNasControl()
    {
        if (!_options.AllowNasControl)
        {
            throw new UnauthorizedAccessException("NAS control is disabled by plugin permission policy.");
        }
    }

    private static bool IsSameOrChildPath(string candidate, string root)
    {
        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;

        var normalizedRoot = EnsureTrailingSeparator(Path.GetFullPath(root));
        var normalizedCandidate = Path.GetFullPath(candidate);

        return string.Equals(normalizedCandidate.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
                normalizedRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar),
                comparison)
            || normalizedCandidate.StartsWith(normalizedRoot, comparison);
    }

    private static string EnsureTrailingSeparator(string path)
    {
        return Path.EndsInDirectorySeparator(path)
            ? path
            : path + Path.DirectorySeparatorChar;
    }
}
