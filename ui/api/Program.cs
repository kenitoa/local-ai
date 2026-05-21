using LocalAI.CloudInterface;
using AspNetAiApi;
using Microsoft.Extensions.FileProviders;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.UseUrls("http://localhost:5088");

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
        policy.AllowAnyOrigin()
            .AllowAnyHeader()
            .AllowAnyMethod());
});

builder.Services.AddHttpClient<OllamaClient>(client =>
{
    client.BaseAddress = new Uri("http://localhost:11434");
    client.Timeout = TimeSpan.FromSeconds(20);
});

builder.Services.AddSingleton<SessionStore>();
builder.Services.AddSingleton<PromptManager>();
builder.Services.AddSingleton<PluginExecutor>();
builder.Services.AddSingleton<RagSearchService>();
builder.Services.AddSingleton<ProjectFolderService>();
builder.Services.AddSingleton<CloudAIInterfaceCatalogService>();
builder.Services.AddHttpClient<AiMarketService>();
builder.Services.AddScoped<ICloudAI>(_ =>
    CloudAIServiceFactory.CreateAsync(CloudAIOptionsFactory.Create()).GetAwaiter().GetResult());
builder.Services.AddScoped<KernelGateway>();
builder.Services.AddScoped<ChatService>();

var app = builder.Build();

app.UseCors();

var webRoot = ResolveWebRoot();
if (webRoot is not null)
{
    var webFiles = new PhysicalFileProvider(webRoot);
    app.UseDefaultFiles(new DefaultFilesOptions { FileProvider = webFiles });
    app.UseStaticFiles(new StaticFileOptions { FileProvider = webFiles });
}

app.MapGet("/", () => webRoot is null
    ? Results.Redirect("/api/health")
    : Results.File(Path.Combine(webRoot, "index.html"), "text/html"));

app.MapGet("/api/health", async (OllamaClient ollama, CancellationToken cancellationToken) =>
{
    var ollamaStatus = await ollama.CheckAsync(cancellationToken);
    return Results.Ok(new HealthResponse(
        "ok",
        "aspnet-api",
        "semantic-kernel-adapter-ready",
        ollamaStatus));
});

app.MapPost("/api/session/new", (SessionStore sessions, NewSessionRequest request) =>
{
    var session = sessions.Create(request.Title);
    return Results.Ok(new NewSessionResponse(session.Id, session.Title, session.CreatedAt));
});

app.MapGet("/api/models", async (OllamaClient ollama, CancellationToken cancellationToken) =>
{
    var models = await ollama.ListModelsAsync(cancellationToken);
    return Results.Ok(new ModelsResponse(models));
});

app.MapGet("/api/cloud-ai/interface", async (
    CloudAIInterfaceCatalogService cloudAiInterface,
    CancellationToken cancellationToken) =>
{
    return Results.Ok(await cloudAiInterface.GetAsync(cancellationToken));
});

app.MapPost("/api/cloud-ai/compositions", async (
    CloudAICompositionCreateRequest request,
    CloudAIInterfaceCatalogService cloudAiInterface,
    CancellationToken cancellationToken) =>
{
    try
    {
        var composition = await cloudAiInterface.CreateCompositionAsync(request, cancellationToken);
        return Results.Created($"/api/cloud-ai/compositions/{Uri.EscapeDataString(composition.Id)}", composition);
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
    catch (InvalidOperationException ex)
    {
        return Results.Conflict(new { error = ex.Message });
    }
});

app.MapGet("/api/market/models", (AiMarketService market) =>
{
    return Results.Ok(new AiMarketModelsResponse(market.List()));
});

app.MapPost("/api/market/models/{id}/download", async (
    string id,
    AiMarketService market,
    CancellationToken cancellationToken) =>
{
    try
    {
        return Results.Ok(await market.DownloadAsync(id, cancellationToken));
    }
    catch (ArgumentException ex)
    {
        return Results.NotFound(new { error = ex.Message });
    }
    catch (InvalidOperationException ex)
    {
        return Results.Conflict(new { error = ex.Message });
    }
});

app.MapDelete("/api/market/models/{id}", async (
    string id,
    AiMarketService market,
    CancellationToken cancellationToken) =>
{
    try
    {
        return Results.Ok(await market.DeleteAsync(id, cancellationToken));
    }
    catch (ArgumentException ex)
    {
        return Results.NotFound(new { error = ex.Message });
    }
    catch (InvalidOperationException ex)
    {
        return Results.Conflict(new { error = ex.Message });
    }
});

app.MapGet("/api/projects", (ProjectFolderService projects) =>
{
    return Results.Ok(new ProjectFoldersResponse(projects.List()));
});

app.MapPost("/api/projects", (ProjectFolderService projects, ProjectFolderCreateRequest request) =>
{
    try
    {
        var project = projects.Create(request.Name);
        return Results.Created($"/api/projects/{Uri.EscapeDataString(project.Name)}", project);
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
    catch (InvalidOperationException ex)
    {
        return Results.Conflict(new { error = ex.Message });
    }
});

app.MapDelete("/api/projects/{name}", (ProjectFolderService projects, string name) =>
{
    try
    {
        return projects.Delete(name)
            ? Results.NoContent()
            : Results.NotFound(new { error = "프로젝트 폴더를 찾을 수 없습니다." });
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
});

app.MapPatch("/api/projects/{name}", (ProjectFolderService projects, string name, ProjectFolderRenameRequest request) =>
{
    try
    {
        return Results.Ok(projects.Rename(name, request.Name));
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
    catch (DirectoryNotFoundException ex)
    {
        return Results.NotFound(new { error = ex.Message });
    }
    catch (InvalidOperationException ex)
    {
        return Results.Conflict(new { error = ex.Message });
    }
});

app.MapPost("/api/projects/{name}/chats", (ProjectFolderService projects, string name, ProjectChatCreateRequest request) =>
{
    try
    {
        var chat = projects.CreateChat(name, request.Title);
        return Results.Created($"/api/projects/{Uri.EscapeDataString(name)}/chats/{chat.Id}", chat);
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
    catch (DirectoryNotFoundException ex)
    {
        return Results.NotFound(new { error = ex.Message });
    }
});

app.MapPost("/api/chat", async (
    ChatRequest request,
    ChatService chatService,
    CancellationToken cancellationToken) =>
{
    var response = await chatService.SendAsync(request, cancellationToken);
    return Results.Ok(response);
});

app.MapPost("/api/chat/stream", async (
    ChatRequest request,
    ChatService chatService,
    HttpResponse response,
    CancellationToken cancellationToken) =>
{
    response.ContentType = "text/event-stream; charset=utf-8";

    await foreach (var chunk in chatService.StreamAsync(request, cancellationToken))
    {
        await response.WriteAsync($"data: {chunk}\n\n", cancellationToken);
        await response.Body.FlushAsync(cancellationToken);
    }
});

app.MapPost("/api/rag/search", (RagSearchRequest request, RagSearchService search) =>
{
    return Results.Ok(search.Search(request));
});

app.MapPost("/api/tools/execute", (ToolExecuteRequest request, PluginExecutor tools) =>
{
    return Results.Ok(tools.Execute(request));
});

app.Run();

static string? ResolveWebRoot()
{
    var contentRoot = Directory.GetCurrentDirectory();
    var publishedWebRoot = Path.Combine(contentRoot, "wwwroot");
    if (File.Exists(Path.Combine(publishedWebRoot, "index.html")))
    {
        return publishedWebRoot;
    }

    var current = new DirectoryInfo(contentRoot);
    while (current is not null)
    {
        var sourceWebRoot = Path.Combine(current.FullName, "apps", "web");
        if (File.Exists(Path.Combine(sourceWebRoot, "index.html")))
        {
            return sourceWebRoot;
        }

        current = current.Parent;
    }

    return null;
}
