using System.Collections.Concurrent;

namespace LocalAI.Core.Vector;

public sealed class InMemoryVectorStore : IVectorStore
{
    private readonly ConcurrentDictionary<string, VectorStoreItem> _items = new();

    public void Upsert(VectorStoreItem item)
    {
        _items[item.Id] = item;
    }

    public IReadOnlyList<VectorStoreSearchResult> Search(
        IReadOnlyDictionary<string, double> queryVector,
        int topK = 5)
    {
        if (queryVector.Count == 0)
        {
            return Array.Empty<VectorStoreSearchResult>();
        }

        return _items.Values
            .Select(item => new
            {
                Item = item,
                Score = Cosine(queryVector, item.Vector)
            })
            .Where(item => item.Score > 0)
            .OrderByDescending(item => item.Score)
            .Take(Math.Clamp(topK, 1, 20))
            .Select(item => new VectorStoreSearchResult(
                item.Item.DocumentId,
                item.Item.Title,
                item.Item.Chunk,
                Math.Round(item.Score, 4)))
            .ToList();
    }

    public void Clear()
    {
        _items.Clear();
    }

    private static double Cosine(
        IReadOnlyDictionary<string, double> left,
        IReadOnlyDictionary<string, double> right)
    {
        if (left.Count == 0 || right.Count == 0)
        {
            return 0;
        }

        var dot = left.Sum(item => right.TryGetValue(item.Key, out var value) ? item.Value * value : 0);
        var leftMagnitude = Math.Sqrt(left.Values.Sum(value => value * value));
        var rightMagnitude = Math.Sqrt(right.Values.Sum(value => value * value));

        return leftMagnitude == 0 || rightMagnitude == 0
            ? 0
            : dot / (leftMagnitude * rightMagnitude);
    }
}
