var candidatePaths = new[]
{
    Path.Combine(AppContext.BaseDirectory, "Microsoft.ML.OnnxRuntime.dll"),
    Path.Combine(Directory.GetCurrentDirectory(), "bin", "Debug", "net9.0", "Microsoft.ML.OnnxRuntime.dll"),
    Path.Combine(AppContext.BaseDirectory, "runtimes", "win-x64", "native", "onnxruntime.dll"),
    Path.Combine(Directory.GetCurrentDirectory(), "bin", "Debug", "net9.0", "runtimes", "win-x64", "native", "onnxruntime.dll")
};

var runtimePath = candidatePaths.FirstOrDefault(File.Exists);
if (runtimePath is null)
{
    Console.WriteLine("ONNX Runtime package payload is not vendored in this offline workspace.");
    Console.WriteLine("The probe project builds without NuGet restore and should be upgraded when package restore is available.");
    return;
}

Console.WriteLine($"ONNX Runtime payload detected: {runtimePath}");
