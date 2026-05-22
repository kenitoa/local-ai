namespace LocalAI.CloudInterface;

public interface ITraceRecorder
{
    Task<RequestTrace> RecordAsync(TraceRecordInput input);
}
