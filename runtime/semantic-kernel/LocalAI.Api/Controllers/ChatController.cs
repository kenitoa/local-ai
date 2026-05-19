using LocalAI.Core.AI;
using LocalAI.Core.Rag;
using LocalAI.OllamaConnector;
using Microsoft.AspNetCore.Mvc;
using System.Net;

namespace LocalAI.Api.Controllers;

[ApiController]
[Route("api")]
public sealed class ChatController(
    IChatService chatService,
    IStreamingChatService streamingChatService,
    IChatSessionStore sessions,
    IRagService rag,
    AiModelOptions modelOptions,
    IOllamaConnector ollamaConnector) : ControllerBase
{
    [HttpPost("chat")]
    public async Task<ActionResult<ChatResponse>> Send(
        [FromBody] ChatRequest request,
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await chatService.SendAsync(request, cancellationToken);
            return Ok(response);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (HttpRequestException ex)
        {
            return StatusCode(
                StatusCodes.Status503ServiceUnavailable,
                ChatErrorResponse.From("ollama-unavailable", ex));
        }
        catch (TaskCanceledException ex)
        {
            return StatusCode(
                StatusCodes.Status504GatewayTimeout,
                ChatErrorResponse.From("ollama-timeout", ex));
        }
    }

    [HttpPost("chat/stream")]
    public async Task Stream(
        [FromBody] ChatRequest request,
        CancellationToken cancellationToken)
    {
        Response.ContentType = "text/event-stream; charset=utf-8";

        try
        {
            await foreach (var chunk in streamingChatService.StreamAsync(request, cancellationToken))
            {
                await WriteSseDataAsync(Response, chunk, cancellationToken);
                await Response.Body.FlushAsync(cancellationToken);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            await WriteSseEventAsync(
                Response,
                "error",
                ChatErrorResponse.From(
                    ex is TaskCanceledException ? "ollama-timeout" : "ollama-unavailable",
                    ex).Message,
                cancellationToken);
            await Response.Body.FlushAsync(cancellationToken);
        }
    }

    [HttpPost("session")]
    public ActionResult<SessionResponse> CreateSession()
    {
        var sessionId = Guid.NewGuid().ToString("N");
        sessions.GetOrCreate(sessionId);
        return Ok(new SessionResponse(sessionId, DateTime.Now));
    }

    [HttpDelete("session/{id}")]
    public IActionResult ClearSession(string id)
    {
        sessions.Clear(id);
        return NoContent();
    }

    [HttpGet("health")]
    public async Task<ActionResult<HealthResponse>> Health(CancellationToken cancellationToken)
    {
        var health = await ollamaConnector.CheckHealthAsync(cancellationToken);

        return Ok(new HealthResponse(
            health.IsReachable
                ? health.ModelInstalled ? "ok" : "model-missing"
                : "ollama-unreachable",
            "local-ai-api",
            modelOptions.Provider,
            health.ModelId,
            health.Endpoint,
            modelOptions.ServiceId,
            modelOptions.TimeoutSeconds,
            modelOptions.EnableFunctionCalling,
            health.ModelInstalled,
            health.InstalledModels,
            health.Error));
    }

    [HttpGet("models")]
    public async Task<ActionResult<ModelsResponse>> Models(CancellationToken cancellationToken)
    {
        var connected = await ollamaConnector.CheckConnectionAsync(cancellationToken);
        var installedModels = connected
            ? await ollamaConnector.GetInstalledModelsAsync(cancellationToken)
            : Array.Empty<string>();

        return Ok(new ModelsResponse(
            installedModels,
            modelOptions.ModelId,
            connected));
    }

    [HttpPost("rag/documents")]
    public ActionResult<RagAddDocumentResponse> AddDocument([FromBody] RagAddDocumentRequest request)
    {
        var id = rag.AddDocument(request.Title, request.Content);
        return Ok(new RagAddDocumentResponse(id));
    }

    [HttpPost("rag/search")]
    public ActionResult<IReadOnlyList<RagSearchResult>> Search([FromBody] RagSearchRequest request)
    {
        return Ok(rag.Search(request.Query, request.TopK ?? 5));
    }

    [HttpPost("tools/execute")]
    public ActionResult<ToolExecuteResponse> ExecuteTool([FromBody] ToolExecuteRequest request)
    {
        var name = request.Name.Trim().ToLowerInvariant();
        return name switch
        {
            "time" => Ok(new ToolExecuteResponse(name, DateTimeOffset.Now.ToString("yyyy-MM-dd HH:mm:ss zzz"), true, null)),
            "health" => Ok(new ToolExecuteResponse(name, "api-ready", true, null)),
            "model" => Ok(new ToolExecuteResponse(name, modelOptions.ModelId, true, null)),
            _ => Ok(new ToolExecuteResponse(request.Name, string.Empty, false, $"Unknown safe tool: {request.Name}"))
        };
    }

    private static async Task WriteSseDataAsync(
        HttpResponse response,
        string data,
        CancellationToken cancellationToken)
    {
        using var reader = new StringReader(data);

        string? line;
        while ((line = await reader.ReadLineAsync(cancellationToken)) is not null)
        {
            await response.WriteAsync($"data: {line}\n", cancellationToken);
        }

        if (data.EndsWith('\n'))
        {
            await response.WriteAsync("data: \n", cancellationToken);
        }

        await response.WriteAsync("\n", cancellationToken);
    }

    private static async Task WriteSseEventAsync(
        HttpResponse response,
        string eventName,
        string data,
        CancellationToken cancellationToken)
    {
        await response.WriteAsync($"event: {eventName}\n", cancellationToken);
        await WriteSseDataAsync(response, data, cancellationToken);
    }
}

public sealed record SessionResponse(string SessionId, DateTime CreatedAt);

public sealed record HealthResponse(
    string Status,
    string Api,
    string Provider,
    string ModelId,
    string Endpoint,
    string ServiceId,
    int TimeoutSeconds,
    bool EnableFunctionCalling,
    bool ModelInstalled,
    IReadOnlyList<string> InstalledModels,
    string? Error);

public sealed record ModelsResponse(
    IReadOnlyList<string> Models,
    string ConfiguredModel,
    bool OllamaReachable);

public sealed record RagAddDocumentRequest(string Title, string Content);

public sealed record RagAddDocumentResponse(string DocumentId);

public sealed record RagSearchRequest(string Query, int? TopK);

public sealed record ToolExecuteRequest(string Name, string? Input);

public sealed record ToolExecuteResponse(
    string Name,
    string Result,
    bool Success,
    string? Error);

public sealed record ChatErrorResponse(
    string Error,
    string Message)
{
    public static ChatErrorResponse From(string error, Exception exception)
    {
        return new ChatErrorResponse(error, NormalizeMessage(exception.Message));
    }

    private static string NormalizeMessage(string message)
    {
        return string.IsNullOrWhiteSpace(message)
            ? "The local Ollama endpoint did not return a usable response."
            : message;
    }
}
