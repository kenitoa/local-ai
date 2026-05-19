using System.Text.RegularExpressions;

namespace LocalAI.Core.Security;

public static partial class SensitiveDataMasker
{
    public static string Mask(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        var masked = EmailPattern().Replace(value, "[email]");
        masked = TokenPattern().Replace(masked, "$1=[secret]");
        return masked;
    }

    [GeneratedRegex(@"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", RegexOptions.IgnoreCase)]
    private static partial Regex EmailPattern();

    [GeneratedRegex(@"(?i)\b(api[_-]?key|token|password|secret)\s*=\s*([^\s;]+)")]
    private static partial Regex TokenPattern();
}
