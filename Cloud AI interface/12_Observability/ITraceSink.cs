namespace LocalAI.CloudInterface;

public interface ITraceSink
{
    Task WriteAsync(RequestTrace trace);
}
