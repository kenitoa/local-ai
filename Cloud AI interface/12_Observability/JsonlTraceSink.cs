using System.Text.Json;

namespace LocalAI.CloudInterface;

public sealed class JsonlTraceSink : ITraceSink
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        WriteIndented = false
    };

    private readonly string path;
    private readonly SemaphoreSlim fileLock = new(1, 1);

    public JsonlTraceSink(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            throw new ArgumentException("Trace JSONL path is required.", nameof(path));
        }

        this.path = path;
    }

    public async Task WriteAsync(RequestTrace trace)
    {
        ArgumentNullException.ThrowIfNull(trace);

        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var line = JsonSerializer.Serialize(trace, SerializerOptions);
        await fileLock.WaitAsync().ConfigureAwait(false);
        try
        {
            await File.AppendAllTextAsync(path, line + Environment.NewLine).ConfigureAwait(false);
        }
        finally
        {
            fileLock.Release();
        }
    }
}
