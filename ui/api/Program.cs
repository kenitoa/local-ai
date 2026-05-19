using AspNetAiApi;

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
builder.Services.AddScoped<KernelGateway>();
builder.Services.AddScoped<ChatService>();

var app = builder.Build();

app.UseCors();

app.MapGet("/", () => Results.Redirect("/api/health"));

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
