namespace LocalAI.CloudInterface;

public sealed class MvpReadinessReport
{
    public IReadOnlyList<MvpFeatureStatus> Features { get; init; } = Array.Empty<MvpFeatureStatus>();
    public bool IsReadyThroughMvp1 => IsReady(1);
    public bool IsReadyThroughMvp2 => IsReady(2);
    public bool IsReadyThroughMvp3 => IsReady(3);
    public bool IsReadyThroughMvp4 => IsReady(4);
    public bool IsReadyThroughMvp5 => IsReady(5);

    public bool IsReady(int mvpLevel)
    {
        return Features
            .Where(feature => feature.MvpLevel <= mvpLevel)
            .All(feature => feature.Implemented);
    }
}
