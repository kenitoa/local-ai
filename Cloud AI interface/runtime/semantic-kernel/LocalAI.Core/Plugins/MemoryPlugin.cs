using System.ComponentModel;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Plugins;

public sealed class MemoryPlugin
{
    private readonly Dictionary<string, string> _items = new(StringComparer.OrdinalIgnoreCase);

    [KernelFunction]
    [Description("Stores a short in-memory preference or note for the current process.")]
    public string Remember(string key, string value)
    {
        _items[key.Trim()] = value.Trim();
        return $"Remembered: {key.Trim()}";
    }

    [KernelFunction]
    [Description("Gets an in-memory preference or note from the current process.")]
    public string Recall(string key)
    {
        return _items.TryGetValue(key.Trim(), out var value) ? value : string.Empty;
    }

    [KernelFunction]
    [Description("Lists in-memory keys for the current process.")]
    public string ListKeys()
    {
        return string.Join(Environment.NewLine, _items.Keys.Order(StringComparer.OrdinalIgnoreCase));
    }

    [KernelFunction]
    [Description("Clears one in-memory preference or note from the current process.")]
    public string Forget(string key)
    {
        return _items.Remove(key.Trim()) ? $"Forgot: {key.Trim()}" : $"Not found: {key.Trim()}";
    }
}
