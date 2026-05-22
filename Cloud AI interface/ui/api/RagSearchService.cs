namespace AspNetAiApi;

public sealed class RagSearchService
{
    private static readonly IReadOnlyList<RagSearchResult> Documents =
    [
        new("api-structure", "ASP.NET API", "UI client traffic is routed through HTTP endpoints before reaching the local AI runtime.", 0.94),
        new("semantic-kernel", "Semantic Kernel Adapter", "Kernel and service construction are isolated behind DI-friendly application services.", 0.87),
        new("ollama", "Ollama Runtime", "The final model call is delegated to the local Ollama HTTP API.", 0.82)
    ];

    public RagSearchResponse Search(RagSearchRequest request)
    {
        var query = string.IsNullOrWhiteSpace(request.Query) ? "api" : request.Query.Trim();
        var topK = Math.Clamp(request.TopK ?? 3, 1, 10);
        var terms = query.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        var results = Documents
            .Select(document => Score(document, terms))
            .OrderByDescending(item => item.Score)
            .Take(topK)
            .Select(item => item.Document with { Score = Math.Round(item.Score, 2) })
            .ToList();

        return new RagSearchResponse(query, results);
    }

    private static (RagSearchResult Document, double Score) Score(RagSearchResult document, string[] terms)
    {
        var haystack = $"{document.Title} {document.Snippet}".ToLowerInvariant();
        var hits = terms.Count(term => haystack.Contains(term.ToLowerInvariant(), StringComparison.Ordinal));
        return (document, document.Score + hits * 0.1);
    }
}
