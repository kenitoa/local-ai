namespace LocalAI.CloudInterface;

public sealed class MemoryUsage
{
    public long RequiredMemoryMb { get; init; }
    public long EstimatedUsedMemoryMb { get; init; }
    public long PeakMemoryMb { get; init; }
}
