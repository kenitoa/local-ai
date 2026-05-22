using LocalAI.Core.Prompts;

namespace LocalAI.Core.AI;

public static class PromptTemplates
{
    public static string DefaultAssistant => SystemPrompts.DefaultAssistant;
    public static string NasAssistant => SystemPrompts.NasAssistant;
    public static string CodingAssistant => SystemPrompts.CodingAssistant;
    public static string RagAnswer => SystemPrompts.RagAnswer;

    public static string Load(string name)
    {
        return SystemPrompts.Load(name);
    }
}
