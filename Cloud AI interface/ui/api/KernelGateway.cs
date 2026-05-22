namespace AspNetAiApi;

public sealed class KernelGateway(OllamaClient ollama)
{
    public async Task<KernelResult> CompleteAsync(
        string model,
        string prompt,
        CancellationToken cancellationToken)
    {
        var response = await ollama.GenerateAsync(model, prompt, cancellationToken);

        if (response.Success)
        {
            return new KernelResult(response.Text, "ollama");
        }

        var fallback = "ASP.NET API 계층은 정상입니다. Ollama 연결이 준비되면 실제 모델 응답으로 교체됩니다.";
        return new KernelResult($"{fallback} 원인: {response.Text}", "api-fallback");
    }
}

public sealed record KernelResult(string Text, string Source);
