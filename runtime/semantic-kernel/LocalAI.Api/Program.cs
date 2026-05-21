using LocalAI.CloudInterface;
using LocalAI.Core.AI;
using LocalAI.Core.Plugins;
using LocalAI.Core.Rag;
using LocalAI.Core.Vector;
using LocalAI.OllamaConnector;
using Microsoft.SemanticKernel;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.UseUrls("http://localhost:5088");
builder.Services.AddControllers();

var modelOptions = ReadAiModelOptions(builder.Configuration);
var cloudAiOptions = ReadCloudAiOptions(builder.Configuration, modelOptions);

var pluginOptions = new PluginPermissionOptions
{
    WorkspaceRoot = builder.Configuration["Plugins:WorkspaceRoot"] ?? Directory.GetCurrentDirectory(),
    NasRootPath = builder.Configuration["Plugins:NasRootPath"] ?? string.Empty,
    AllowFileDelete = bool.TryParse(builder.Configuration["Plugins:AllowFileDelete"], out var allowFileDelete) && allowFileDelete,
    AllowCommandExecution = bool.TryParse(builder.Configuration["Plugins:AllowCommandExecution"], out var allowCommandExecution) && allowCommandExecution,
    AllowNasControl = bool.TryParse(builder.Configuration["Plugins:AllowNasControl"], out var allowNasControl) && allowNasControl,
};

builder.Services.AddSingleton(modelOptions);
builder.Services.AddSingleton(cloudAiOptions);
builder.Services.AddSingleton(pluginOptions);
builder.Services.AddSingleton(modelOptions.ToOllamaConnectorOptions());
builder.Services.AddSingleton<IOllamaConnector>(sp =>
    new SemanticKernelOllamaConnector(sp.GetRequiredService<OllamaConnectorOptions>()));
builder.Services.AddSingleton(sp => KernelFactory.Create(
    sp.GetRequiredService<IOllamaConnector>(),
    sp.GetRequiredService<PluginPermissionOptions>()));
builder.Services.AddSingleton<IChatSessionStore, InMemoryChatSessionStore>();
builder.Services.AddSingleton<SemanticKernelChatService>();
builder.Services.AddSingleton<IChatService>(sp => sp.GetRequiredService<SemanticKernelChatService>());
builder.Services.AddSingleton<IStreamingChatService>(sp => sp.GetRequiredService<SemanticKernelChatService>());
builder.Services.AddSingleton<IVectorStore, InMemoryVectorStore>();
builder.Services.AddSingleton<IRagService, InMemoryRagService>();
builder.Services.AddSingleton<ICloudAI>(_ =>
    CloudAIServiceFactory.CreateAsync(cloudAiOptions).GetAwaiter().GetResult());

var app = builder.Build();

app.MapControllers();
app.MapGet("/", () => Results.Redirect("/api/health"));

app.Run();

static AiModelOptions ReadAiModelOptions(IConfiguration configuration)
{
    var aiModel = configuration.GetSection("AiModel");
    var ollama = configuration.GetSection("Ollama");

    return new AiModelOptions
    {
        Provider = Read("Provider", "Ollama"),
        ModelId = Read("ModelId", "llama3.1"),
        Endpoint = Read("Endpoint", "http://localhost:11434"),
        ServiceId = Read("ServiceId", "local-ollama"),
        TimeoutSeconds = int.TryParse(Read("TimeoutSeconds", "180"), out var timeoutSeconds)
            ? timeoutSeconds
            : 180,
        EnableFunctionCalling = bool.TryParse(Read("EnableFunctionCalling", "true"), out var enableFunctionCalling)
            ? enableFunctionCalling
            : true,
        ApiKey = Read("ApiKey", string.Empty)
    };

    string Read(string key, string fallback)
    {
        var value = aiModel[key];
        if (!string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        value = ollama[key];
        return string.IsNullOrWhiteSpace(value) ? fallback : value;
    }
}

static CloudAIServiceOptions ReadCloudAiOptions(
    IConfiguration configuration,
    AiModelOptions modelOptions)
{
    var root = FindRepositoryRoot();
    var section = configuration.GetSection("CloudAI");

    return new CloudAIServiceOptions
    {
        ExpertRegistryPath = ReadPath("ExpertRegistryPath", Path.Combine("Cloud AI interface", "Configuration", "expert-registry.json")),
        CompositionProfilesPath = ReadPath("CompositionProfilesPath", Path.Combine("Cloud AI interface", "Configuration", "composition-profiles.json")),
        FallbackChainsPath = ReadPath("FallbackChainsPath", Path.Combine("Cloud AI interface", "Configuration", "fallback-chains.json")),
        ExpertPermissionsPath = ReadPath("ExpertPermissionsPath", Path.Combine("Cloud AI interface", "Configuration", "expert-permissions.json")),
        LocalModelRootPath = ReadPath("LocalModelRootPath", "local LLM model"),
        OllamaModelStorePath = ReadPath("OllamaModelStorePath", Path.Combine("runtime", "ollama", "server", "models")),
        OllamaEndpoint = modelOptions.Endpoint,
        DefaultOllamaModelId = modelOptions.ModelId,
        MvpLevel = int.TryParse(section["MvpLevel"], out var mvpLevel) ? mvpLevel : 4,
        EnableSelfOptimization = bool.TryParse(section["EnableSelfOptimization"], out var selfOptimization) && selfOptimization
    };

    string? ReadPath(string key, string relativePath)
    {
        var configured = section[key];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return configured;
        }

        return root is null ? null : Path.Combine(root, relativePath);
    }
}

static string? FindRepositoryRoot()
{
    var current = new DirectoryInfo(Directory.GetCurrentDirectory());
    while (current is not null)
    {
        if (Directory.Exists(Path.Combine(current.FullName, "Cloud AI interface")) &&
            Directory.Exists(Path.Combine(current.FullName, "runtime")))
        {
            return current.FullName;
        }

        current = current.Parent;
    }

    return null;
}
