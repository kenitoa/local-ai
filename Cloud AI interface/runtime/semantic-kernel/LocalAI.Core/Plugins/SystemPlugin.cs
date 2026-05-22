using System.ComponentModel;
using Microsoft.SemanticKernel;

namespace LocalAI.Core.Plugins;

public sealed class SystemPlugin
{
    [KernelFunction]
    [Description("Returns whether the local AI system plugin is ready.")]
    public string GetStatus() => "Local AI system plugin is ready.";

    [KernelFunction]
    [Description("Returns the current local server time.")]
    public string GetCurrentTime()
    {
        return DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
    }

    [KernelFunction]
    [Description("Returns the operating system version.")]
    public string GetOperatingSystem()
    {
        return Environment.OSVersion.ToString();
    }

    [KernelFunction]
    [Description("현재 운영체제 정보를 반환한다.")]
    public string GetOSInfo()
    {
        return GetOperatingSystem();
    }

    [KernelFunction]
    [Description("Returns a compact runtime summary without secrets.")]
    public string GetRuntimeSummary()
    {
        return $"Machine={Environment.MachineName}; OS={Environment.OSVersion}; .NET={Environment.Version}; 64Bit={Environment.Is64BitProcess}";
    }
}
