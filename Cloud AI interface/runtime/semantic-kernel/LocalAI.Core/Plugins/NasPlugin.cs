using System.ComponentModel;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Plugins;

public sealed class NasPlugin(PluginPermissionGuard? permissions = null)
{
    private readonly PluginPermissionGuard _permissions = permissions ?? new PluginPermissionGuard();

    public string RootPath { get; init; } = string.Empty;

    [KernelFunction]
    [Description("Returns the configured NAS root path.")]
    public string GetRootPath()
    {
        return string.IsNullOrWhiteSpace(RootPath) ? "NAS root is not configured." : RootPath;
    }

    [KernelFunction]
    [Description("Checks whether the configured NAS root is reachable.")]
    public string GetStatus()
    {
        if (string.IsNullOrWhiteSpace(RootPath))
        {
            return "NAS root is not configured.";
        }

        return Directory.Exists(RootPath)
            ? $"NAS root is reachable: {RootPath}"
            : $"NAS root is not reachable: {RootPath}";
    }

    [KernelFunction]
    [Description("Returns available disk space for the configured NAS root.")]
    public string GetStorageSummary()
    {
        if (string.IsNullOrWhiteSpace(RootPath) || !Directory.Exists(RootPath))
        {
            return "NAS root is not reachable.";
        }

        var root = Path.GetPathRoot(Path.GetFullPath(RootPath));
        if (string.IsNullOrWhiteSpace(root))
        {
            return "NAS drive root could not be resolved.";
        }

        var drive = new DriveInfo(root);
        return $"Drive={drive.Name}; AvailableBytes={drive.AvailableFreeSpace}; TotalBytes={drive.TotalSize}";
    }

    [KernelFunction]
    [Description("Checks NAS-control permission before any external NAS control flow is allowed.")]
    public string RequireControlPermission(string operation)
    {
        _permissions.DemandNasControl();
        return $"NAS control permission granted for: {operation}";
    }
}
