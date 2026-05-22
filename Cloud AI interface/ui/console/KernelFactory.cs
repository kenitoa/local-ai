namespace ConsoleValidation;

public sealed class KernelFactory(ConsoleLogger logger)
{
    public string Create()
    {
        var enabled = Environment.GetEnvironmentVariable("SEMANTIC_KERNEL_ENABLED");
        if (string.Equals(enabled, "true", StringComparison.OrdinalIgnoreCase))
        {
            logger.Info("KernelFactory", "Semantic Kernel 연결 플래그가 켜져 있습니다.");
            return "connected";
        }

        logger.Warn("KernelFactory", "Semantic Kernel 패키지 연결 전 단계입니다. Console 검증 구조만 확인합니다.");
        return "adapter-ready";
    }
}
