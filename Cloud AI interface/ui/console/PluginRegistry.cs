namespace ConsoleValidation;

public sealed class PluginRegistry(ConsoleLogger logger)
{
    private readonly Dictionary<string, Func<string, string>> plugins = new(StringComparer.OrdinalIgnoreCase);

    public void RegisterDefaults()
    {
        Register("time", _ => DateTimeOffset.Now.ToString("yyyy-MM-dd HH:mm:ss zzz"));
        Register("echo", input => input);
    }

    public void Register(string name, Func<string, string> handler)
    {
        plugins[name] = handler;
        logger.Info("Plugin", $"{name} 플러그인을 등록했습니다.");
    }

    public string Invoke(string name, string input)
    {
        if (!plugins.TryGetValue(name, out var handler))
        {
            throw new InvalidOperationException($"{name} 플러그인이 등록되어 있지 않습니다.");
        }

        var result = handler(input);
        logger.Info("Plugin", $"{name} 플러그인을 호출했습니다.");
        return result;
    }
}
