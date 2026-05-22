namespace LocalAI.CloudInterface;

public interface IExpertHistoryProvider
{
    ExpertHistoricalStats GetStats(string expertId);
}
