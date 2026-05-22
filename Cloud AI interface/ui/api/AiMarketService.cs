using System.Diagnostics;

namespace AspNetAiApi;

public sealed class AiMarketService(HttpClient httpClient)
{
    private readonly string runtimeRoot = Path.Combine(CloudAIOptionsFactory.RepositoryRoot ?? Directory.GetCurrentDirectory(), "runtime");

    public IReadOnlyList<AiMarketModelDto> List()
    {
        EnsureRuntimeFolders();
        return Catalog.Select(ToDto).ToArray();
    }

    public async Task<AiMarketOperationResponse> DownloadAsync(string id, CancellationToken cancellationToken)
    {
        var item = Find(id);
        EnsureRuntimeFolders();

        if (item.Kind.Equals("ollama", StringComparison.OrdinalIgnoreCase))
        {
            return await RunOllamaAsync("pull", item.ModelId, cancellationToken);
        }

        if (item.DownloadUrl is null)
        {
            throw new InvalidOperationException("This model does not have a direct download URL.");
        }

        var targetPath = GetTargetPath(item);
        Directory.CreateDirectory(Path.GetDirectoryName(targetPath)!);

        await using var source = await httpClient.GetStreamAsync(item.DownloadUrl, cancellationToken);
        await using var target = File.Create(targetPath);
        await source.CopyToAsync(target, cancellationToken);

        return new AiMarketOperationResponse(
            item.Id,
            "downloaded",
            $"Downloaded to {Path.GetRelativePath(runtimeRoot, targetPath)}",
            ToDto(item));
    }

    public async Task<AiMarketOperationResponse> DeleteAsync(string id, CancellationToken cancellationToken)
    {
        var item = Find(id);
        EnsureRuntimeFolders();

        if (item.Kind.Equals("ollama", StringComparison.OrdinalIgnoreCase))
        {
            return await RunOllamaAsync("rm", item.ModelId, cancellationToken);
        }

        var targetPath = GetTargetPath(item);
        EnsureUnderRuntime(targetPath);
        if (File.Exists(targetPath))
        {
            File.Delete(targetPath);
        }

        return new AiMarketOperationResponse(
            item.Id,
            "deleted",
            $"Deleted {Path.GetRelativePath(runtimeRoot, targetPath)}",
            ToDto(item));
    }

    private async Task<AiMarketOperationResponse> RunOllamaAsync(
        string command,
        string modelId,
        CancellationToken cancellationToken)
    {
        var modelsPath = Path.Combine(runtimeRoot, "ollama", "server", "models");
        Directory.CreateDirectory(modelsPath);

        var startInfo = new ProcessStartInfo
        {
            FileName = ResolveOllamaExecutable(),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        startInfo.ArgumentList.Add(command);
        startInfo.ArgumentList.Add(modelId);
        startInfo.Environment["OLLAMA_MODELS"] = modelsPath;
        startInfo.Environment["OLLAMA_HOST"] = "127.0.0.1:11434";

        using var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Failed to start ollama process.");
        var outputTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var errorTask = process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);

        var output = await outputTask;
        var error = await errorTask;
        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? output : error);
        }

        var item = Catalog.First(entry => entry.ModelId.Equals(modelId, StringComparison.OrdinalIgnoreCase));
        return new AiMarketOperationResponse(
            item.Id,
            command == "pull" ? "downloaded" : "deleted",
            string.IsNullOrWhiteSpace(output) ? $"{command} {modelId}" : output.Trim(),
            ToDto(item));
    }

    private AiMarketModelEntry Find(string id)
    {
        return Catalog.FirstOrDefault(item => item.Id.Equals(id, StringComparison.OrdinalIgnoreCase))
            ?? throw new ArgumentException($"Unknown market model id: {id}");
    }

    private string ResolveOllamaExecutable()
    {
        var bundled = Path.Combine(runtimeRoot, "ollama", "server", "cli", OperatingSystem.IsWindows() ? "ollama.exe" : "ollama");
        if (File.Exists(bundled))
        {
            return bundled;
        }

        return OperatingSystem.IsWindows() ? "ollama.exe" : "ollama";
    }

    private AiMarketModelDto ToDto(AiMarketModelEntry item)
    {
        var targetPath = GetTargetPath(item);
        var installed = item.Kind.Equals("ollama", StringComparison.OrdinalIgnoreCase)
            ? File.Exists(GetOllamaManifestPath(item.ModelId))
            : File.Exists(targetPath);

        return new AiMarketModelDto(
            item.Id,
            item.Name,
            item.Provider,
            item.Kind,
            item.Category,
            item.ModelId,
            item.Description,
            item.License,
            item.SourceUrl,
            Path.GetRelativePath(runtimeRoot, targetPath),
            installed);
    }

    private string GetTargetPath(AiMarketModelEntry item)
    {
        var path = item.Kind.ToLowerInvariant() switch
        {
            "ollama" => Path.Combine(runtimeRoot, "ollama", "server", "models"),
            "onnx" => Path.Combine(runtimeRoot, "dotnet", "models", "onnx", item.FileName ?? $"{item.Id}.onnx"),
            "mlnet" => Path.Combine(runtimeRoot, "dotnet", "models", "mlnet", item.FileName ?? $"{item.Id}.zip"),
            _ => Path.Combine(runtimeRoot, item.Kind, item.FileName ?? item.Id)
        };

        EnsureUnderRuntime(path);
        return path;
    }

    private string GetOllamaManifestPath(string modelId)
    {
        var parts = modelId.Split(':', 2);
        var name = parts[0];
        var tag = parts.Length > 1 ? parts[1] : "latest";
        return Path.Combine(runtimeRoot, "ollama", "server", "models", "manifests", "registry.ollama.ai", "library", name, tag);
    }

    private void EnsureRuntimeFolders()
    {
        Directory.CreateDirectory(Path.Combine(runtimeRoot, "ollama", "server", "models"));
        Directory.CreateDirectory(Path.Combine(runtimeRoot, "dotnet", "models", "onnx"));
        Directory.CreateDirectory(Path.Combine(runtimeRoot, "dotnet", "models", "mlnet"));
    }

    private void EnsureUnderRuntime(string path)
    {
        var root = Path.GetFullPath(runtimeRoot);
        var fullPath = Path.GetFullPath(path);
        if (!fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Model path must stay under runtime.");
        }
    }

    private static readonly AiMarketModelEntry[] Catalog =
    [
        new("ollama-tinyllama-1-1b", "TinyLlama 1.1B", "Ollama", "ollama", "chat-small", "tinyllama:1.1b", "Very small chat model for quick local smoke tests and low-memory devices.", "Apache-2.0", "https://ollama.com/library/tinyllama"),
        new("ollama-llama3-2-1b", "Llama 3.2 1B", "Ollama", "ollama", "chat-small", "llama3.2:1b", "Small general chat model for fast local assistants.", "Meta Llama community license", "https://ollama.com/library/llama3.2"),
        new("ollama-llama3-2-3b", "Llama 3.2 3B", "Ollama", "ollama", "chat", "llama3.2:3b", "Small general chat model for local assistants.", "Meta Llama community license", "https://ollama.com/library/llama3.2"),
        new("ollama-llama3-1-8b", "Llama 3.1 8B", "Ollama", "ollama", "chat", "llama3.1:8b", "General chat and summarization model for stronger local responses.", "Meta Llama community license", "https://ollama.com/library/llama3.1"),
        new("ollama-qwen2-5-0-5b", "Qwen2.5 0.5B", "Ollama", "ollama", "chat-small", "qwen2.5:0.5b", "Tiny multilingual chat model for very fast tests.", "Apache-2.0 family", "https://ollama.com/library/qwen2.5"),
        new("ollama-qwen2-5-3b", "Qwen2.5 3B", "Ollama", "ollama", "chat-code", "qwen2.5:3b", "General reasoning and Korean/English coding chat model.", "Apache-2.0 family", "https://ollama.com/library/qwen2.5"),
        new("ollama-qwen2-5-7b", "Qwen2.5 7B", "Ollama", "ollama", "chat-code", "qwen2.5:7b", "Balanced multilingual reasoning and coding model.", "Apache-2.0 family", "https://ollama.com/library/qwen2.5"),
        new("ollama-qwen3-0-6b", "Qwen3 0.6B", "Ollama", "ollama", "reasoning-small", "qwen3:0.6b", "Small Qwen3 reasoning model for low-memory experimentation.", "Apache-2.0 family", "https://ollama.com/library/qwen3"),
        new("ollama-qwen3-4b", "Qwen3 4B", "Ollama", "ollama", "reasoning", "qwen3:4b", "Compact reasoning model with multilingual capability.", "Apache-2.0 family", "https://ollama.com/library/qwen3"),
        new("ollama-gemma3-1b", "Gemma 3 1B", "Ollama", "ollama", "chat-small", "gemma3:1b", "Very compact instruction model for lightweight local use.", "Gemma terms of use", "https://ollama.com/library/gemma3"),
        new("ollama-qwen2-5-coder-7b", "Qwen2.5 Coder 7B", "Ollama", "ollama", "coding", "qwen2.5-coder:7b", "Code generation and code reasoning model.", "Apache-2.0 family", "https://ollama.com/library/qwen2.5-coder"),
        new("ollama-qwen2-5-coder-1-5b", "Qwen2.5 Coder 1.5B", "Ollama", "ollama", "coding-small", "qwen2.5-coder:1.5b", "Small code assistant for local development workflows.", "Apache-2.0 family", "https://ollama.com/library/qwen2.5-coder"),
        new("ollama-qwen3-coder", "Qwen3 Coder", "Ollama", "ollama", "coding", "qwen3-coder:latest", "Agentic coding model for code generation and repository work.", "Apache-2.0 family", "https://ollama.com/library/qwen3-coder"),
        new("ollama-codellama-7b", "Code Llama 7B", "Ollama", "ollama", "coding", "codellama:7b", "Code generation and code discussion model.", "Code Llama license", "https://ollama.com/library/codellama"),
        new("ollama-starcoder2-3b", "StarCoder2 3B", "Ollama", "ollama", "coding-small", "starcoder2:3b", "Small code model for completion and code-focused prompts.", "BigCode OpenRAIL-M family", "https://ollama.com/library/starcoder2"),
        new("ollama-starcoder2-7b", "StarCoder2 7B", "Ollama", "ollama", "coding", "starcoder2:7b", "Code model for stronger local code completion and reasoning.", "BigCode OpenRAIL-M family", "https://ollama.com/library/starcoder2"),
        new("ollama-deepseek-coder-6-7b", "DeepSeek Coder 6.7B", "Ollama", "ollama", "coding", "deepseek-coder:6.7b", "Code-specialized model for generation and analysis.", "DeepSeek model license", "https://ollama.com/library/deepseek-coder"),
        new("ollama-gemma3-4b", "Gemma 3 4B", "Ollama", "ollama", "chat", "gemma3:4b", "Compact general instruction model.", "Gemma terms of use", "https://ollama.com/library/gemma3"),
        new("ollama-mistral-7b", "Mistral 7B", "Ollama", "ollama", "chat", "mistral:7b", "General purpose local language model.", "Apache-2.0", "https://ollama.com/library/mistral"),
        new("ollama-mistral-nemo-12b", "Mistral Nemo 12B", "Ollama", "ollama", "chat", "mistral-nemo:12b", "Stronger multilingual general model for larger local machines.", "Apache-2.0", "https://ollama.com/library/mistral-nemo"),
        new("ollama-phi3-mini", "Phi-3 Mini", "Ollama", "ollama", "chat-small", "phi3:mini", "Small Microsoft Phi model for local reasoning and chat tests.", "MIT model license family", "https://ollama.com/library/phi3"),
        new("ollama-phi4-mini", "Phi-4 Mini", "Ollama", "ollama", "chat", "phi4-mini:latest", "Compact Phi-4 family model for local productivity prompts.", "MIT model license family", "https://ollama.com/library/phi4-mini"),
        new("ollama-deepseek-r1-1-5b", "DeepSeek R1 1.5B", "Ollama", "ollama", "reasoning", "deepseek-r1:1.5b", "Small reasoning model for local experimentation.", "MIT model license family", "https://ollama.com/library/deepseek-r1"),
        new("ollama-deepseek-r1-7b", "DeepSeek R1 7B", "Ollama", "ollama", "reasoning", "deepseek-r1:7b", "Reasoning model for stronger local chain-of-thought style tasks.", "MIT model license family", "https://ollama.com/library/deepseek-r1"),
        new("ollama-mathstral-7b", "Mathstral 7B", "Ollama", "ollama", "math", "mathstral:7b", "Math-focused model for symbolic and numerical reasoning prompts.", "Apache-2.0", "https://ollama.com/library/mathstral"),
        new("ollama-olmo2-7b", "OLMo 2 7B", "Ollama", "ollama", "chat", "olmo2:7b", "Open language model family for general local experimentation.", "Apache-2.0", "https://ollama.com/library/olmo2"),
        new("ollama-llama3-2-vision-11b", "Llama 3.2 Vision 11B", "Ollama", "ollama", "vision", "llama3.2-vision:11b", "Vision-language model for image-aware local workflows.", "Meta Llama community license", "https://ollama.com/library/llama3.2-vision"),
        new("ollama-llava-7b", "LLaVA 7B", "Ollama", "ollama", "vision", "llava:7b", "Vision-language assistant for image analysis experiments.", "Apache-2.0 family", "https://ollama.com/library/llava"),
        new("ollama-nomic-embed-text", "nomic-embed-text", "Ollama", "ollama", "embedding", "nomic-embed-text:latest", "Embedding model for RAG and semantic search.", "Apache-2.0", "https://ollama.com/library/nomic-embed-text"),
        new("ollama-mxbai-embed-large", "mxbai-embed-large", "Ollama", "ollama", "embedding", "mxbai-embed-large:latest", "Large embedding model for retrieval workflows.", "Apache-2.0 family", "https://ollama.com/library/mxbai-embed-large"),
        new("ollama-bge-m3", "BGE-M3", "Ollama", "ollama", "embedding", "bge-m3:latest", "Multilingual and multi-function embedding model for RAG.", "MIT model license family", "https://ollama.com/library/bge-m3"),
        new("ollama-qwen3-embedding-0-6b", "Qwen3 Embedding 0.6B", "Ollama", "ollama", "embedding", "qwen3-embedding:0.6b", "Small multilingual embedding model for retrieval and code search.", "Apache-2.0 family", "https://ollama.com/library/qwen3-embedding"),
        new("ollama-qwen3-embedding-4b", "Qwen3 Embedding 4B", "Ollama", "ollama", "embedding", "qwen3-embedding:4b", "Larger multilingual embedding model for higher quality retrieval.", "Apache-2.0 family", "https://ollama.com/library/qwen3-embedding"),
        new("ollama-all-minilm", "all-minilm", "Ollama", "ollama", "embedding-small", "all-minilm:latest", "Small sentence embedding model for fast semantic search.", "Apache-2.0 family", "https://ollama.com/library/all-minilm"),
        new("ollama-snowflake-arctic-embed", "Snowflake Arctic Embed", "Ollama", "ollama", "embedding", "snowflake-arctic-embed:latest", "Retrieval embedding model for document search workflows.", "Apache-2.0", "https://ollama.com/library/snowflake-arctic-embed"),
        new("ollama-granite-embedding", "Granite Embedding", "Ollama", "ollama", "embedding", "granite-embedding:latest", "IBM Granite embedding model for retrieval and RAG workflows.", "Apache-2.0", "https://ollama.com/library/granite-embedding"),
        new("ollama-embeddinggemma", "EmbeddingGemma", "Ollama", "ollama", "embedding", "embeddinggemma:latest", "Gemma-family embedding model for local semantic retrieval.", "Gemma terms of use", "https://ollama.com/library/embeddinggemma"),
        new("onnx-squeezenet", "SqueezeNet ONNX", "ONNX Model Zoo", "onnx", "vision", "squeezenet1.0-3", "Small image classification model for .NET ONNX runtime checks.", "BSD-style research/model license", "https://github.com/onnx/models", "https://huggingface.co/onnxmodelzoo/squeezenet1.0-3/resolve/main/squeezenet1.0-3.onnx", "squeezenet1.0-3.onnx"),
        new("onnx-minilm-l6-v2", "all-MiniLM-L6-v2 ONNX", "Sentence Transformers / Xenova", "onnx", "embedding", "all-MiniLM-L6-v2", "ONNX sentence embedding model for .NET embedding pipeline experiments.", "Apache-2.0", "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2", "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx", "all-MiniLM-L6-v2.onnx"),
        new("onnx-bge-small-en-v1-5", "BGE Small EN v1.5 ONNX", "BAAI / Xenova", "onnx", "embedding", "bge-small-en-v1.5", "Small English embedding model for .NET ONNX retrieval tests.", "MIT model license family", "https://huggingface.co/BAAI/bge-small-en-v1.5", "https://huggingface.co/Xenova/bge-small-en-v1.5/resolve/main/onnx/model.onnx", "bge-small-en-v1.5.onnx")
    ];

    private sealed record AiMarketModelEntry(
        string Id,
        string Name,
        string Provider,
        string Kind,
        string Category,
        string ModelId,
        string Description,
        string License,
        string SourceUrl,
        string? DownloadUrl = null,
        string? FileName = null);
}

public sealed record AiMarketModelDto(
    string Id,
    string Name,
    string Provider,
    string Kind,
    string Category,
    string ModelId,
    string Description,
    string License,
    string SourceUrl,
    string TargetPath,
    bool Installed);

public sealed record AiMarketModelsResponse(IReadOnlyList<AiMarketModelDto> Models);

public sealed record AiMarketOperationResponse(
    string ModelId,
    string Status,
    string Message,
    AiMarketModelDto Model);
