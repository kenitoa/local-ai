namespace LocalAI.CloudInterface;

public sealed class LocalModelCatalog
{
    public IReadOnlyList<ExpertDefinition> Discover(CloudAIServiceOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);

        if (!options.EnableLocalModelDiscovery)
        {
            return Array.Empty<ExpertDefinition>();
        }

        var definitions = new List<ExpertDefinition>();
        definitions.AddRange(DiscoverSemanticKernelRuntime(options));
        definitions.AddRange(DiscoverOllamaModels(options));
        definitions.AddRange(DiscoverFileModels(options.LocalModelRootPath));

        return definitions
            .GroupBy(definition => definition.Profile.Id, StringComparer.OrdinalIgnoreCase)
            .Select(group => group.First())
            .ToArray();
    }

    private static IEnumerable<ExpertDefinition> DiscoverSemanticKernelRuntime(CloudAIServiceOptions options)
    {
        if (string.IsNullOrWhiteSpace(options.LocalModelRootPath) ||
            !Directory.Exists(options.LocalModelRootPath))
        {
            yield break;
        }

        var semanticKernelPath = Path.Combine(options.LocalModelRootPath, "Semantic Kernel");
        if (!Directory.Exists(semanticKernelPath))
        {
            yield break;
        }

        yield return new ExpertDefinition
        {
            Profile = new ExpertProfile
            {
                Id = "semantic-kernel-local-ollama",
                Provider = "ollama",
                ModelType = "llm",
                Capabilities = ["chat", "reasoning", "code", "korean", "local-runtime"],
                Priority = 13,
                CostScore = 1.0,
                LatencyScore = 0.74,
                QualityScore = 0.76,
                RequiredMemoryMb = 4096,
                SupportsStreaming = true,
                SupportsJsonOutput = true
            },
            ModelPath = semanticKernelPath,
            Endpoint = options.OllamaEndpoint,
            KeepAlive = true,
            Settings = new Dictionary<string, object>
            {
                ["modelId"] = options.DefaultOllamaModelId,
                ["serviceId"] = "cloud-ai-local-semantic-kernel",
                ["source"] = "local-llm-model-semantic-kernel"
            }
        };
    }

    private static IEnumerable<ExpertDefinition> DiscoverOllamaModels(CloudAIServiceOptions options)
    {
        if (string.IsNullOrWhiteSpace(options.OllamaModelStorePath) ||
            !Directory.Exists(options.OllamaModelStorePath))
        {
            yield break;
        }

        var manifestsRoot = Path.Combine(options.OllamaModelStorePath, "manifests");
        if (!Directory.Exists(manifestsRoot))
        {
            yield break;
        }

        foreach (var manifestPath in Directory.EnumerateFiles(manifestsRoot, "*", SearchOption.AllDirectories))
        {
            var modelId = ToOllamaModelId(manifestPath, manifestsRoot);
            if (string.IsNullOrWhiteSpace(modelId))
            {
                continue;
            }

            yield return CreateOllamaDefinition(modelId, manifestPath, options);
        }
    }

    private static IEnumerable<ExpertDefinition> DiscoverFileModels(string? localModelRoot)
    {
        if (string.IsNullOrWhiteSpace(localModelRoot) || !Directory.Exists(localModelRoot))
        {
            yield break;
        }

        foreach (var modelPath in Directory.EnumerateFiles(localModelRoot, "*.*", SearchOption.AllDirectories))
        {
            var extension = Path.GetExtension(modelPath);
            if (!IsLocalModelFile(extension))
            {
                continue;
            }

            yield return CreateFileModelDefinition(modelPath, extension);
        }
    }

    private static ExpertDefinition CreateOllamaDefinition(
        string modelId,
        string manifestPath,
        CloudAIServiceOptions options)
    {
        return new ExpertDefinition
        {
            Profile = new ExpertProfile
            {
                Id = ToExpertId("ollama", modelId),
                Provider = "ollama",
                ModelType = "llm",
                Capabilities = InferOllamaCapabilities(modelId),
                Priority = 20,
                CostScore = 1.0,
                LatencyScore = 0.7,
                QualityScore = 0.75,
                RequiredMemoryMb = 4096,
                SupportsStreaming = true,
                SupportsJsonOutput = true
            },
            ModelPath = manifestPath,
            Endpoint = options.OllamaEndpoint,
            KeepAlive = true,
            Settings = new Dictionary<string, object>
            {
                ["modelId"] = modelId,
                ["modelStorePath"] = options.OllamaModelStorePath ?? string.Empty,
                ["source"] = "ollama-manifest"
            }
        };
    }

    private static ExpertDefinition CreateFileModelDefinition(string modelPath, string extension)
    {
        var fileName = Path.GetFileNameWithoutExtension(modelPath);
        var provider = extension.Equals(".onnx", StringComparison.OrdinalIgnoreCase)
            ? "onnx-local"
            : "mlnet-local";

        return new ExpertDefinition
        {
            Profile = new ExpertProfile
            {
                Id = ToExpertId(provider, fileName),
                Provider = provider,
                ModelType = extension.Equals(".onnx", StringComparison.OrdinalIgnoreCase) ? "onnx" : "classifier",
                Capabilities = ["intent-classification", "classification", "local-model"],
                Priority = 35,
                CostScore = 1.0,
                LatencyScore = 0.85,
                QualityScore = 0.65,
                RequiredMemoryMb = 512,
                SupportsJsonOutput = true
            },
            ModelPath = modelPath,
            KeepAlive = true,
            Settings = new Dictionary<string, object>
            {
                ["source"] = "local-model-file",
                ["extension"] = extension
            }
        };
    }

    private static string ToOllamaModelId(string manifestPath, string manifestsRoot)
    {
        var relative = Path.GetRelativePath(manifestsRoot, manifestPath);
        var parts = relative.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            .Where(part => !string.IsNullOrWhiteSpace(part))
            .ToArray();

        if (parts.Length < 2)
        {
            return string.Empty;
        }

        var modelName = parts[^2];
        var tag = parts[^1];
        return $"{modelName}:{tag}";
    }

    private static string[] InferOllamaCapabilities(string modelId)
    {
        var normalized = modelId.ToLowerInvariant();
        var capabilities = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "chat",
            "reasoning"
        };

        if (normalized.Contains("code") || normalized.Contains("coder") || normalized.Contains("qwen"))
        {
            capabilities.Add("code");
        }

        if (normalized.Contains("embed"))
        {
            capabilities.Add("embedding");
        }

        if (normalized.Contains("llama") || normalized.Contains("qwen"))
        {
            capabilities.Add("korean");
        }

        return capabilities.ToArray();
    }

    private static bool IsLocalModelFile(string extension)
    {
        return extension.Equals(".onnx", StringComparison.OrdinalIgnoreCase)
            || extension.Equals(".zip", StringComparison.OrdinalIgnoreCase)
            || extension.Equals(".mlnet", StringComparison.OrdinalIgnoreCase);
    }

    private static string ToExpertId(string provider, string value)
    {
        var chars = value.ToLowerInvariant()
            .Select(ch => char.IsLetterOrDigit(ch) ? ch : '-')
            .ToArray();
        var normalized = new string(chars).Trim('-');

        while (normalized.Contains("--", StringComparison.Ordinal))
        {
            normalized = normalized.Replace("--", "-", StringComparison.Ordinal);
        }

        return $"{provider}-{normalized}";
    }
}
