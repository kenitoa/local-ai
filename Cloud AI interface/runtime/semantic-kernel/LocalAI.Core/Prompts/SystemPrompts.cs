namespace LocalAI.Core.Prompts;

public static class SystemPrompts
{
    private const string PromptDirectoryName = "Prompts";

    public static string DefaultAssistant => Load("default-assistant");
    public static string NasAssistant => Load("nas-assistant");
    public static string CodingAssistant => Load("coding-assistant");
    public static string RagAnswer => Load("rag-answer");

    public static string Load(string name)
    {
        var fileName = NormalizeFileName(name);

        foreach (var directory in GetPromptDirectories())
        {
            var path = Path.Combine(directory, fileName);
            if (File.Exists(path))
            {
                return File.ReadAllText(path).Trim();
            }
        }

        throw new FileNotFoundException($"Prompt file '{fileName}' was not found in the prompt directories.");
    }

    private static string NormalizeFileName(string name)
    {
        var trimmed = name.Trim();
        var fileName = Path.GetFileName(trimmed);

        if (string.IsNullOrWhiteSpace(fileName))
        {
            throw new ArgumentException("Prompt name cannot be empty.", nameof(name));
        }

        if (!fileName.EndsWith(".txt", StringComparison.OrdinalIgnoreCase))
        {
            fileName += ".txt";
        }

        return fileName;
    }

    private static IEnumerable<string> GetPromptDirectories()
    {
        yield return Path.Combine(AppContext.BaseDirectory, PromptDirectoryName);
        yield return Path.Combine(Directory.GetCurrentDirectory(), PromptDirectoryName);
    }
}
