using System.Text.Json;
using LocalAI.CloudInterface;

namespace AspNetAiApi;

public sealed class CloudAIInterfaceCatalogService
{
    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public async Task<CloudAIInterfaceResponse> GetAsync(CancellationToken cancellationToken)
    {
        var options = CloudAIOptionsFactory.Create();
        var definitions = await LoadDefinitionsAsync(options, cancellationToken);
        var compositions = await LoadCompositionsAsync(options, cancellationToken);
        var models = definitions
            .Select(ToModel)
            .OrderBy(model => model.ProviderRank)
            .ThenBy(model => model.Name, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return new CloudAIInterfaceResponse(
            "Cloud AI Interface",
            CloudAIOptionsFactory.RepositoryRoot,
            options.ExpertRegistryPath,
            options.CompositionProfilesPath,
            models.FirstOrDefault(model => model.Capabilities.Contains("local-runtime", StringComparer.OrdinalIgnoreCase)),
            models,
            compositions.Select(ToComposition).ToArray());
    }

    public async Task<CloudAICompositionDto> CreateCompositionAsync(
        CloudAICompositionCreateRequest request,
        CancellationToken cancellationToken)
    {
        var options = CloudAIOptionsFactory.Create();
        if (string.IsNullOrWhiteSpace(options.CompositionProfilesPath))
        {
            throw new InvalidOperationException("Cloud AI composition profile path is not configured.");
        }

        var definitions = await LoadDefinitionsAsync(options, cancellationToken);
        var expertIds = request.ExpertIds?
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Select(id => id.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray() ?? Array.Empty<string>();

        if (expertIds.Length < 2)
        {
            throw new ArgumentException("A composition requires at least two experts.");
        }

        var availableIds = definitions
            .Select(definition => definition.Profile.Id)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var missing = expertIds.Where(id => !availableIds.Contains(id)).ToArray();
        if (missing.Length > 0)
        {
            throw new ArgumentException($"Unknown expert id: {string.Join(", ", missing)}");
        }

        var expertIdSet = expertIds.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var strategy = NormalizeStrategy(request.Strategy, expertIds.Length);
        var fallback = request.Fallback?
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Select(id => id.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray() ?? InferFallback(definitions, expertIdSet);
        var compositionId = string.IsNullOrWhiteSpace(request.CompositionId)
            ? $"web-{Slugify(request.Name)}-{DateTimeOffset.UtcNow:yyyyMMddHHmmss}"
            : Slugify(request.CompositionId);

        var entry = new CompositionProfileEntry
        {
            CompositionId = compositionId,
            Experts = expertIds,
            Strategy = strategy,
            Fallback = fallback,
            RequiresJudge = strategy is CompositionStrategy.ParallelJudge or CompositionStrategy.ParallelVote ||
                expertIds.Any(id => id.Contains("judge", StringComparison.OrdinalIgnoreCase)),
            RunInParallel = strategy is CompositionStrategy.ParallelJudge or CompositionStrategy.ParallelVote
        };

        var document = await LoadCompositionDocumentAsync(options.CompositionProfilesPath, cancellationToken);
        document.Compositions.RemoveAll(existing =>
            existing.CompositionId.Equals(entry.CompositionId, StringComparison.OrdinalIgnoreCase));
        document.Compositions.Add(entry);

        Directory.CreateDirectory(Path.GetDirectoryName(options.CompositionProfilesPath)!);
        await using var output = File.Create(options.CompositionProfilesPath);
        await JsonSerializer.SerializeAsync(output, document, SerializerOptions, cancellationToken);

        return ToComposition(entry);
    }

    private static async Task<IReadOnlyList<ExpertDefinition>> LoadDefinitionsAsync(
        CloudAIServiceOptions options,
        CancellationToken cancellationToken)
    {
        var definitions = new List<ExpertDefinition>();
        if (!string.IsNullOrWhiteSpace(options.ExpertRegistryPath) &&
            File.Exists(options.ExpertRegistryPath))
        {
            await using var stream = File.OpenRead(options.ExpertRegistryPath);
            var document = await JsonSerializer.DeserializeAsync<ExpertRegistryDocument>(
                stream,
                SerializerOptions,
                cancellationToken) ?? new ExpertRegistryDocument();
            definitions.AddRange(document.Experts.Select(ExpertDefinitionMapper.FromRegistryEntry));
        }

        definitions.AddRange(new LocalModelCatalog().Discover(options));

        return definitions
            .GroupBy(definition => definition.Profile.Id, StringComparer.OrdinalIgnoreCase)
            .Select(group => group.OrderByDescending(definition => definition.ModelPath is not null).First())
            .ToArray();
    }

    private static async Task<IReadOnlyList<CompositionProfileEntry>> LoadCompositionsAsync(
        CloudAIServiceOptions options,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(options.CompositionProfilesPath))
        {
            return Array.Empty<CompositionProfileEntry>();
        }

        var document = await LoadCompositionDocumentAsync(options.CompositionProfilesPath, cancellationToken);
        return document.Compositions;
    }

    private static async Task<CompositionProfileDocument> LoadCompositionDocumentAsync(
        string path,
        CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            return new CompositionProfileDocument();
        }

        await using var stream = File.OpenRead(path);
        return await JsonSerializer.DeserializeAsync<CompositionProfileDocument>(
            stream,
            SerializerOptions,
            cancellationToken) ?? new CompositionProfileDocument();
    }

    private static CloudAIModelDto ToModel(ExpertDefinition definition)
    {
        var profile = definition.Profile;
        var modelId = ReadSetting(definition, "modelId") ?? profile.Id;
        var name = ToDisplayName(modelId, profile.Id);
        return new CloudAIModelDto(
            $"expert:{profile.Id}",
            profile.Id,
            name,
            profile.Provider,
            profile.ModelType,
            profile.Capabilities,
            ToTypeLabel(profile.Provider),
            ToSpecialty(profile),
            ToDescription(profile, modelId),
            definition.ModelPath ?? ToRoute(profile.Provider),
            modelId,
            profile.ModelType is not "embedding",
            profile.SupportsStreaming,
            profile.SupportsJsonOutput,
            profile.RequiredMemoryMb,
            definition.Endpoint,
            ProviderRank(profile.Provider));
    }

    private static CloudAICompositionDto ToComposition(CompositionProfileEntry entry)
    {
        return new CloudAICompositionDto(
            entry.CompositionId,
            entry.CompositionId,
            entry.Experts.Select(id => $"expert:{id}").ToArray(),
            entry.Experts,
            entry.Strategy,
            entry.Fallback,
            entry.RequiresJudge ?? false,
            entry.RunInParallel ?? false);
    }

    private static string NormalizeStrategy(string? strategy, int expertCount)
    {
        if (string.IsNullOrWhiteSpace(strategy))
        {
            return expertCount > 2 ? CompositionStrategy.ParallelJudge : CompositionStrategy.Pipeline;
        }

        return strategy.Trim().ToLowerInvariant() switch
        {
            CompositionStrategy.Single => CompositionStrategy.Single,
            CompositionStrategy.Pipeline => CompositionStrategy.Pipeline,
            CompositionStrategy.ParallelVote => CompositionStrategy.ParallelVote,
            CompositionStrategy.ParallelJudge => CompositionStrategy.ParallelJudge,
            CompositionStrategy.FallbackChain => CompositionStrategy.FallbackChain,
            _ => throw new ArgumentException($"Unknown composition strategy: {strategy}")
        };
    }

    private static string[] InferFallback(IEnumerable<ExpertDefinition> definitions, ISet<string> expertIds)
    {
        var fallback = definitions
            .Where(definition => !expertIds.Contains(definition.Profile.Id))
            .OrderBy(definition => definition.Profile.Priority)
            .Select(definition => definition.Profile.Id)
            .Take(1)
            .ToArray();
        return fallback.Length > 0 ? fallback : Array.Empty<string>();
    }

    private static string? ReadSetting(ExpertDefinition definition, string key)
    {
        if (!definition.Settings.TryGetValue(key, out var value))
        {
            return null;
        }

        return value switch
        {
            JsonElement element => element.ValueKind == JsonValueKind.String ? element.GetString() : element.ToString(),
            _ => value?.ToString()
        };
    }

    private static string ToDisplayName(string modelId, string expertId)
    {
        var display = modelId.Contains(':', StringComparison.Ordinal)
            ? modelId.Split(':')[0]
            : modelId;
        return string.IsNullOrWhiteSpace(display) ? expertId : display;
    }

    private static string ToTypeLabel(string provider)
    {
        return provider.ToLowerInvariant() switch
        {
            "ollama" => "Ollama",
            "mlnet" or "mlnet-local" => "ML.NET",
            "onnx-local" => "ONNX",
            "custom-dotnet" => ".NET",
            "external-api" => "External API",
            "rule-based" => "Rule",
            _ => provider
        };
    }

    private static string ToSpecialty(ExpertProfile profile)
    {
        if (profile.Capabilities.Length == 0)
        {
            return profile.ModelType;
        }

        return string.Join(" / ", profile.Capabilities.Take(3));
    }

    private static string ToDescription(ExpertProfile profile, string modelId)
    {
        return profile.Provider.ToLowerInvariant() switch
        {
            "ollama" => $"{modelId} local Ollama expert exposed through Cloud AI Interface.",
            "custom-dotnet" => $"{profile.Id} .NET expert hidden behind the common Expert interface.",
            "mlnet" or "mlnet-local" => $"{profile.Id} ML.NET classifier expert mapped into Cloud AI Interface.",
            "onnx-local" => $"{profile.Id} ONNX local model expert mapped into Cloud AI Interface.",
            _ => $"{profile.Id} expert registered in Cloud AI Interface."
        };
    }

    private static string ToRoute(string provider)
    {
        return provider.ToLowerInvariant() switch
        {
            "ollama" => "runtime/ollama/server/models",
            "custom-dotnet" => "Cloud AI interface/05_Experts",
            "mlnet" or "mlnet-local" or "onnx-local" => "local LLM model",
            _ => "Cloud AI interface/Configuration"
        };
    }

    private static int ProviderRank(string provider)
    {
        return provider.ToLowerInvariant() switch
        {
            "ollama" => 1,
            "custom-dotnet" => 2,
            "mlnet" or "mlnet-local" or "onnx-local" => 3,
            "external-api" => 4,
            "rule-based" => 5,
            _ => 10
        };
    }

    private static string Slugify(string? value)
    {
        var source = string.IsNullOrWhiteSpace(value) ? "composition" : value.Trim();
        var chars = source.ToLowerInvariant()
            .Select(ch => char.IsLetterOrDigit(ch) ? ch : '-')
            .ToArray();
        var slug = new string(chars).Trim('-');

        while (slug.Contains("--", StringComparison.Ordinal))
        {
            slug = slug.Replace("--", "-", StringComparison.Ordinal);
        }

        return string.IsNullOrWhiteSpace(slug) ? "composition" : slug;
    }
}

public sealed record CloudAIInterfaceResponse(
    string Name,
    string? RepositoryRoot,
    string? ExpertRegistryPath,
    string? CompositionProfilesPath,
    CloudAIModelDto? SemanticKernel,
    IReadOnlyList<CloudAIModelDto> Models,
    IReadOnlyList<CloudAICompositionDto> Compositions);

public sealed record CloudAIModelDto(
    string Key,
    string ExpertId,
    string Name,
    string Provider,
    string ModelType,
    IReadOnlyList<string> Capabilities,
    string TypeLabel,
    string Specialty,
    string Description,
    string Route,
    string ModelId,
    bool Runnable,
    bool SupportsStreaming,
    bool SupportsJsonOutput,
    long RequiredMemoryMb,
    string? Endpoint,
    int ProviderRank);

public sealed record CloudAICompositionDto(
    string Id,
    string Name,
    IReadOnlyList<string> Parts,
    IReadOnlyList<string> ExpertIds,
    string Strategy,
    IReadOnlyList<string> Fallback,
    bool RequiresJudge,
    bool RunInParallel);

public sealed record CloudAICompositionCreateRequest(
    string? CompositionId,
    string? Name,
    IReadOnlyList<string>? ExpertIds,
    string? Strategy,
    IReadOnlyList<string>? Fallback);
