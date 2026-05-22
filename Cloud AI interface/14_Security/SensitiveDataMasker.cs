using System.Text.RegularExpressions;

namespace LocalAI.CloudInterface;

public static partial class SensitiveDataMasker
{
    public static string Mask(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return value;
        }

        var masked = EmailRegex().Replace(value, "[masked-email]");
        masked = TokenRegex().Replace(masked, "$1[masked-secret]");
        masked = BearerRegex().Replace(masked, "Bearer [masked-token]");
        return masked;
    }

    public static Dictionary<string, object> MaskMetadata(IReadOnlyDictionary<string, object> metadata)
    {
        return metadata.ToDictionary(
            item => item.Key,
            item => item.Value is string text ? Mask(text) : item.Value,
            StringComparer.OrdinalIgnoreCase);
    }

    [GeneratedRegex("[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", RegexOptions.IgnoreCase)]
    private static partial Regex EmailRegex();

    [GeneratedRegex("(?i)(api[_-]?key|token|secret|password)\\s*[:=]\\s*([^\\s,;]+)")]
    private static partial Regex TokenRegex();

    [GeneratedRegex("(?i)Bearer\\s+[A-Za-z0-9._~+/=-]+")]
    private static partial Regex BearerRegex();
}
