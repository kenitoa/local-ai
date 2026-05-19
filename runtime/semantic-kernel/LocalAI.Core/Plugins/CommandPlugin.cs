using System.ComponentModel;
using System.Diagnostics;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Plugins;

public sealed class CommandPlugin(PluginPermissionGuard? permissions = null)
{
    private readonly PluginPermissionGuard _permissions = permissions ?? new PluginPermissionGuard();

    [KernelFunction]
    [Description("Explains the command execution permission policy.")]
    public string GetExecutionPolicy()
    {
        return "Command execution is denied unless PluginPermissionOptions.AllowCommandExecution is enabled and the command is allowed.";
    }

    [KernelFunction]
    [Description("Runs an allow-listed command only when command execution is explicitly allowed.")]
    public async Task<string> RunAsync(string command, string arguments = "", int timeoutSeconds = 30)
    {
        _permissions.DemandCommandExecution(command);

        using var process = new Process();
        process.StartInfo = new ProcessStartInfo
        {
            FileName = command,
            Arguments = arguments,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        process.Start();

        var completed = await Task.Run(() => process.WaitForExit(Math.Clamp(timeoutSeconds, 1, 120) * 1000));
        if (!completed)
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException($"Command timed out after {timeoutSeconds} seconds: {command}");
        }

        var output = await process.StandardOutput.ReadToEndAsync();
        var error = await process.StandardError.ReadToEndAsync();

        return string.IsNullOrWhiteSpace(error)
            ? output.Trim()
            : $"{output.Trim()}{Environment.NewLine}{error.Trim()}".Trim();
    }
}
