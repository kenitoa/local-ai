using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Connectors.OpenAI;

namespace LocalAI.Core.AI;

public static class ChatExecutionSettings
{
    public static PromptExecutionSettings? Create(bool enableFunctionCalling)
    {
        return enableFunctionCalling ? CreateAutoFunctionCalling() : null;
    }

    public static PromptExecutionSettings CreateAutoFunctionCalling()
    {
        return new OpenAIPromptExecutionSettings
        {
            FunctionChoiceBehavior = FunctionChoiceBehavior.Auto()
        };
    }
}
