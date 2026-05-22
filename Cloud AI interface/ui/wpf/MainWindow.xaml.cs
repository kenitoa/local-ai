using System.IO;
using System.Text;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace WpfDesktopMvp;

public partial class MainWindow : Window
{
    private const string DesktopHost = "local-ai.desktop";

    public MainWindow()
    {
        InitializeComponent();
        Loaded += MainWindow_Loaded;
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        try
        {
            var webRoot = FindWebRoot();
            var logPath = ResolveWebViewLogPath();
            LoadingText.Text = $"loading {webRoot}";

            var userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "LocalAI",
                "WebView2");
            Directory.CreateDirectory(userDataFolder);

            var environment = await CoreWebView2Environment.CreateAsync(
                browserExecutableFolder: null,
                userDataFolder: userDataFolder);

            await DesktopWebView.EnsureCoreWebView2Async(environment);
            ConfigureWebView(webRoot, logPath);

            DesktopWebView.CoreWebView2.NavigationCompleted += (_, args) =>
            {
                if (args.IsSuccess)
                {
                    AppendLog(logPath, "navigation completed");
                    LoadingOverlay.Visibility = Visibility.Collapsed;
                    return;
                }

                AppendLog(logPath, $"navigation failed: {args.WebErrorStatus}");
                LoadingText.Text = $"desktop interface failed to load: {args.WebErrorStatus}";
            };

            DesktopWebView.Source = new Uri($"https://{DesktopHost}/index.html");
        }
        catch (Exception ex)
        {
            LoadingText.Text = $"desktop interface failed to start: {ex.Message}";
        }
    }

    private void ConfigureWebView(string webRoot, string logPath)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        AppendLog(logPath, $"web root: {webRoot}");

        DesktopWebView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            DesktopHost,
            webRoot,
            CoreWebView2HostResourceAccessKind.Allow);

        DesktopWebView.CoreWebView2.Settings.AreDevToolsEnabled = true;
        DesktopWebView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        DesktopWebView.CoreWebView2.Settings.IsStatusBarEnabled = false;

        DesktopWebView.CoreWebView2.WebMessageReceived += (_, args) =>
        {
            AppendLog(logPath, $"web message: {args.TryGetWebMessageAsString()}");
        };

        _ = DesktopWebView.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync("""
            (() => {
              const send = (level, message) => {
                try {
                  chrome.webview.postMessage(`[${level}] ${String(message)}`);
                } catch {}
              };
              const originalError = console.error.bind(console);
              console.error = (...args) => {
                send("console.error", args.map(String).join(" "));
                originalError(...args);
              };
              window.addEventListener("error", (event) => {
                send("error", `${event.message} at ${event.filename}:${event.lineno}:${event.colno}`);
              });
              window.addEventListener("unhandledrejection", (event) => {
                send("unhandledrejection", event.reason?.message || event.reason || "unknown rejection");
              });
            })();
            """);

        DesktopWebView.CoreWebView2.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
        DesktopWebView.CoreWebView2.WebResourceResponseReceived += async (_, args) =>
        {
            try
            {
                var statusCode = args.Response.StatusCode;
                if (statusCode >= 400)
                {
                    AppendLog(logPath, $"resource {statusCode}: {args.Request.Uri}");
                }
            }
            catch (Exception ex)
            {
                AppendLog(logPath, $"resource log failed: {ex.Message}");
            }

            await Task.CompletedTask;
        };
    }

    private static string FindWebRoot()
    {
        var candidates = GetBaseDirectories()
            .SelectMany(baseDirectory => new[]
            {
                Path.Combine(baseDirectory, "apps", "web"),
                Path.Combine(baseDirectory, "publish", "app", "api", "wwwroot"),
                Path.Combine(baseDirectory, "app", "api", "wwwroot"),
                Path.Combine(baseDirectory, "wwwroot")
            })
            .Distinct(StringComparer.OrdinalIgnoreCase);

        foreach (var candidate in candidates)
        {
            if (File.Exists(Path.Combine(candidate, "index.html")))
            {
                return Path.GetFullPath(candidate);
            }
        }

        throw new FileNotFoundException(
            "apps/web/index.html or publish/app/api/wwwroot/index.html was not found.");
    }

    private static string ResolveWebViewLogPath()
    {
        foreach (var directory in GetBaseDirectories())
        {
            var publishRoot = Path.Combine(directory, "publish");
            if (Directory.Exists(publishRoot))
            {
                return Path.Combine(publishRoot, "logs", "wpf.webview.log");
            }
        }

        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "LocalAI",
            "logs",
            "wpf.webview.log");
    }

    private static void AppendLog(string logPath, string message)
    {
        var line = $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss.fff zzz}] {message}{Environment.NewLine}";
        File.AppendAllText(logPath, line, Encoding.UTF8);
    }

    private static IEnumerable<string> GetBaseDirectories()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var start in new[] { AppContext.BaseDirectory, Environment.CurrentDirectory })
        {
            var directory = new DirectoryInfo(start);
            while (directory is not null)
            {
                var fullName = directory.FullName;
                if (seen.Add(fullName))
                {
                    yield return fullName;
                }

                directory = directory.Parent;
            }
        }
    }
}
