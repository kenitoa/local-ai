using System.ComponentModel;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Plugins;

public sealed class SearchPlugin(PluginPermissionGuard? permissions = null)
{
    private readonly PluginPermissionGuard _permissions = permissions ?? new PluginPermissionGuard();

    [KernelFunction]
    [Description("Searches workspace text files for a query and returns compact matches.")]
    public string SearchText(string query, string directory = ".", string searchPattern = "*.*", int maxResults = 20)
    {
        if (string.IsNullOrWhiteSpace(query))
        {
            return string.Empty;
        }

        var resolvedDirectory = _permissions.ResolveWorkspacePath(directory);
        if (!Directory.Exists(resolvedDirectory))
        {
            return string.Empty;
        }

        var results = new List<string>();
        foreach (var file in Directory.EnumerateFiles(resolvedDirectory, searchPattern, SearchOption.AllDirectories))
        {
            if (results.Count >= Math.Clamp(maxResults, 1, 100))
            {
                break;
            }

            TryCollectMatches(file, query, results, maxResults);
        }

        return string.Join(Environment.NewLine, results);
    }

    private void TryCollectMatches(string file, string query, List<string> results, int maxResults)
    {
        try
        {
            var lineNumber = 0;
            foreach (var line in File.ReadLines(file))
            {
                lineNumber++;
                if (!line.Contains(query, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var relative = Path.GetRelativePath(_permissions.WorkspaceRoot, file);
                results.Add($"{relative}:{lineNumber}: {line.Trim()}");
                if (results.Count >= Math.Clamp(maxResults, 1, 100))
                {
                    return;
                }
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
