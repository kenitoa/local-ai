using LocalAI.OllamaConnector;
using LocalAI.Core.Plugins;
using LocalAI.Core.Security;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.AI;

public static class KernelFactory
{
    public static Kernel Create(
        AiModelOptions? modelOptions = null,
        PluginPermissionOptions? pluginOptions = null)
    {
        modelOptions ??= new AiModelOptions();

        if (!modelOptions.Provider.Equals("Ollama", StringComparison.OrdinalIgnoreCase) &&
            !modelOptions.Provider.Equals("OpenAICompatible", StringComparison.OrdinalIgnoreCase))
        {
            throw new NotSupportedException($"AI provider is not supported yet: {modelOptions.Provider}");
        }

        var connector = new SemanticKernelOllamaConnector(modelOptions.ToOllamaConnectorOptions());
        return Create(connector, pluginOptions);
    }

    public static Kernel Create(
        IOllamaConnector connector,
        PluginPermissionOptions? pluginOptions = null)
    {
        pluginOptions ??= new PluginPermissionOptions();

        var permissions = new PluginPermissionGuard(pluginOptions);

        var kernel = connector.CreateKernel(builder => AddPlugins(builder, permissions, pluginOptions));
        var filter = new PluginSecurityFilter(new PluginSecurityOptions());
        kernel.FunctionInvocationFilters.Add(filter);
        kernel.AutoFunctionInvocationFilters.Add(filter);

        return kernel;
    }

    private static void AddPlugins(
        IKernelBuilder builder,
        PluginPermissionGuard permissions,
        PluginPermissionOptions pluginOptions)
    {
        builder.Plugins.AddFromObject(new SystemPlugin(), "system");
        builder.Plugins.AddFromObject(new FilePlugin(permissions), "file");
        builder.Plugins.AddFromObject(new NasPlugin(permissions)
        {
            RootPath = pluginOptions.NasRootPath
        }, "nas");
        builder.Plugins.AddFromObject(new SearchPlugin(permissions), "search");
        builder.Plugins.AddFromObject(new MemoryPlugin(), "memory");
        builder.Plugins.AddFromObject(new CommandPlugin(permissions), "command");
    }
}
