using System.Diagnostics;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Security;

public sealed class PluginSecurityFilter(PluginSecurityOptions options) :
    IFunctionInvocationFilter,
    IAutoFunctionInvocationFilter
{
    public async Task OnFunctionInvocationAsync(
        FunctionInvocationContext context,
        Func<FunctionInvocationContext, Task> next)
    {
        Validate(context.Function);
        Log("function", context.Function);
        await next(context);
    }

    public async Task OnAutoFunctionInvocationAsync(
        AutoFunctionInvocationContext context,
        Func<AutoFunctionInvocationContext, Task> next)
    {
        Validate(context.Function);
        Log("auto-function", context.Function);
        await next(context);
    }

    private void Validate(KernelFunction function)
    {
        var key = $"{function.PluginName}.{function.Name}";
        if (options.RequireConfirmationForSensitiveFunctions &&
            options.SensitiveFunctions.Contains(key))
        {
            throw new UnauthorizedAccessException(
                $"Sensitive function '{key}' must be invoked through an explicit confirmed command or UI action.");
        }
    }

    private void Log(string category, KernelFunction function)
    {
        if (!options.LogFunctionCalls)
        {
            return;
        }

        var key = SensitiveDataMasker.Mask($"{function.PluginName}.{function.Name}");
        Debug.WriteLine($"SemanticKernel {category}: {key}");
    }
}
