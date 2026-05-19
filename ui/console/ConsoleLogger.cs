namespace ConsoleValidation;

public sealed class ConsoleLogger
{
    public void Info(string area, string message) => Write("INFO", area, message);

    public void Warn(string area, string message) => Write("WARN", area, message);

    public void Error(string area, string message) => Write("ERROR", area, message);

    private static void Write(string level, string area, string message)
    {
        Console.WriteLine($"[{DateTimeOffset.Now:HH:mm:ss}] {level,-5} {area,-18} {message}");
    }
}
