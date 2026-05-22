using System.ComponentModel;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Plugins;

public sealed class FilePlugin(PluginPermissionGuard? permissions = null)
{
    private readonly PluginPermissionGuard _permissions = permissions ?? new PluginPermissionGuard();

    [KernelFunction]
    [Description("Checks whether a workspace file exists.")]
    public bool Exists(string path)
    {
        return File.Exists(_permissions.ResolveWorkspacePath(path));
    }

    [KernelFunction]
    [Description("Reads a UTF-8 text file from the workspace.")]
    public string ReadText(string path, int maxCharacters = 8000)
    {
        var resolvedPath = _permissions.ResolveWorkspacePath(path);
        var content = File.ReadAllText(resolvedPath);

        return content.Length <= maxCharacters
            ? content
            : content[..maxCharacters];
    }

    [KernelFunction]
    [Description("Lists files under a workspace directory.")]
    public string ListFiles(string directory = ".", string searchPattern = "*", int maxResults = 50)
    {
        var resolvedDirectory = _permissions.ResolveWorkspacePath(directory);
        if (!Directory.Exists(resolvedDirectory))
        {
            return string.Empty;
        }

        var files = Directory
            .EnumerateFiles(resolvedDirectory, searchPattern, SearchOption.TopDirectoryOnly)
            .Take(Math.Clamp(maxResults, 1, 200))
            .Select(path => Path.GetRelativePath(_permissions.WorkspaceRoot, path));

        return string.Join(Environment.NewLine, files);
    }

    [KernelFunction]
    [Description("Deletes a workspace file only when destructive file operations are explicitly allowed.")]
    public string DeleteFile(string path)
    {
        _permissions.DemandFileDelete();

        var resolvedPath = _permissions.ResolveWorkspacePath(path);
        File.Delete(resolvedPath);

        return $"Deleted: {Path.GetRelativePath(_permissions.WorkspaceRoot, resolvedPath)}";
    }
}
