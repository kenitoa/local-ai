using LocalAI.Core.Vector;
using System.Text.RegularExpressions;

namespace LocalAI.Core.Rag;

public sealed partial class InMemoryRagService(IVectorStore vectorStore) : IRagService
{
    private const int ChunkSize = 900;
    private const int ChunkOverlap = 120;

    public string AddDocument(string title, string content)
    {
        if (string.IsNullOrWhiteSpace(content))
        {
            throw new ArgumentException("Document content cannot be empty.", nameof(content));
        }

        var id = Guid.NewGuid().ToString("N");
        var document = new RagDocument(
            id,
            string.IsNullOrWhiteSpace(title) ? "Untitled document" : title.Trim(),
            content,
            DateTime.Now);

        var index = 0;
        foreach (var chunk in SplitChunks(content))
        {
            vectorStore.Upsert(new VectorStoreItem(
                $"{document.Id}:{index:D4}",
                document.Id,
                document.Title,
                chunk,
                Vectorize(chunk),
                DateTime.Now));
            index++;
        }

        return id;
    }

    public IReadOnlyList<RagSearchResult> Search(string query, int topK = 5)
    {
        if (string.IsNullOrWhiteSpace(query))
        {
            return Array.Empty<RagSearchResult>();
        }

        var queryVector = Vectorize(query);
        return vectorStore
            .Search(queryVector, topK)
            .Select(item => new RagSearchResult(
                item.DocumentId,
                item.Title,
                item.Chunk,
                item.Score))
            .ToList();
    }

    private static IEnumerable<string> SplitChunks(string content)
    {
        var normalized = content.Replace("\r\n", "\n").Trim();
        if (normalized.Length <= ChunkSize)
        {
            yield return normalized;
            yield break;
        }

        for (var start = 0; start < normalized.Length; start += ChunkSize - ChunkOverlap)
        {
            var length = Math.Min(ChunkSize, normalized.Length - start);
            yield return normalized.Substring(start, length).Trim();

            if (start + length >= normalized.Length)
            {
                yield break;
            }
        }
    }

    private static Dictionary<string, double> Vectorize(string text)
    {
        var vector = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        foreach (Match match in TokenPattern().Matches(text))
        {
            var token = match.Value.ToLowerInvariant();
            vector[token] = vector.GetValueOrDefault(token) + 1;
        }

        return vector;
    }

    [GeneratedRegex(@"[\p{L}\p{N}_\-\.]+")]
    private static partial Regex TokenPattern();
}
