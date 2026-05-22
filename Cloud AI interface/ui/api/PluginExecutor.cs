namespace AspNetAiApi;

public sealed class PluginExecutor
{
    public ToolExecuteResponse Execute(ToolExecuteRequest request)
    {
        var name = request.Name.Trim().ToLowerInvariant();

        return name switch
        {
            "time" => new ToolExecuteResponse("time", DateTimeOffset.Now.ToString("yyyy-MM-dd HH:mm:ss zzz"), true, null),
            "echo" => new ToolExecuteResponse("echo", request.Input ?? "", true, null),
            "health" => new ToolExecuteResponse("health", "api-ready", true, null),
            _ => new ToolExecuteResponse(request.Name, "", false, $"Unknown tool: {request.Name}")
        };
    }
}
