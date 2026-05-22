namespace LocalAI.Core.Rag;

public interface IRagService
{
    string AddDocument(string title, string content);
    IReadOnlyList<RagSearchResult> Search(string query, int topK = 5);
}
