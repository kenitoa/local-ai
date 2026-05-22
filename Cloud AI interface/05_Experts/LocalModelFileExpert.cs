namespace LocalAI.CloudInterface;

public sealed class LocalModelFileExpert : ExpertAdapterBase
{
    public LocalModelFileExpert(ExpertDefinition definition)
        : base(definition.Profile, request => InvokeLocalModelAsync(definition, request))
    {
    }

    private static Task<ExpertResult> InvokeLocalModelAsync(
        ExpertDefinition definition,
        ExpertRequest request)
    {
        if (string.IsNullOrWhiteSpace(definition.ModelPath) || !File.Exists(definition.ModelPath))
        {
            return Task.FromResult(new ExpertResult
            {
                ExpertId = definition.Profile.Id,
                Succeeded = false,
                Confidence = 0,
                Error = "Local ML.NET/ONNX model file is not available."
            });
        }

        var output = new Dictionary<string, object>
        {
            ["modelPath"] = definition.ModelPath,
            ["provider"] = definition.Profile.Provider,
            ["input"] = request.Input,
            ["result"] = "local model mapped"
        };

        return Task.FromResult(new ExpertResult
        {
            ExpertId = definition.Profile.Id,
            Output = System.Text.Json.JsonSerializer.Serialize(output),
            Confidence = 0.6,
            Succeeded = true,
            IsJsonOutput = true,
            Metadata = new Dictionary<string, object>
            {
                ["modelPath"] = definition.ModelPath,
                ["provider"] = definition.Profile.Provider
            }
        });
    }
}
