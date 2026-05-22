namespace LocalAI.Core.Vector;

public interface IVectorStore
{
    void Upsert(VectorStoreItem item);
    IReadOnlyList<VectorStoreSearchResult> Search(IReadOnlyDictionary<string, double> queryVector, int topK = 5);
    void Clear();
}
