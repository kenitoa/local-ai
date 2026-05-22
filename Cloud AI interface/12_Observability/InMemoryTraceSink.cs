using System.Collections.Concurrent;

namespace LocalAI.CloudInterface;

public sealed class InMemoryTraceSink : ITraceSink
{
    private readonly ConcurrentQueue<RequestTrace> traces = new();

    public Task WriteAsync(RequestTrace trace)
    {
        ArgumentNullException.ThrowIfNull(trace);

        traces.Enqueue(trace);
        return Task.CompletedTask;
    }

    public IReadOnlyList<RequestTrace> Snapshot()
    {
        return traces.ToArray();
    }
}
