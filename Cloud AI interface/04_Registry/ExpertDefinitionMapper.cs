namespace LocalAI.CloudInterface;

public static class ExpertDefinitionMapper
{
    public static ExpertDefinition FromRegistryEntry(ExpertRegistryEntry entry)
    {
        ArgumentNullException.ThrowIfNull(entry);

        return new ExpertDefinition
        {
            Profile = entry.ToProfile(),
            ModelPath = entry.ModelPath,
            Endpoint = entry.Endpoint,
            Preload = entry.Preload,
            KeepAlive = entry.KeepAlive,
            Settings = entry.Settings
        };
    }

    public static ExpertDefinition FromExpert(IExpert expert)
    {
        ArgumentNullException.ThrowIfNull(expert);

        return new ExpertDefinition
        {
            Profile = expert.Profile
        };
    }
}
