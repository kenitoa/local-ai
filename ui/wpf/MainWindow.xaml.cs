using System.Collections.ObjectModel;
using System.Windows;
using Microsoft.Win32;

namespace WpfDesktopMvp;

public partial class MainWindow : Window
{
    private readonly ObservableCollection<ChatMessageView> chatMessages = new();
    private readonly ObservableCollection<string> logs = new();
    private readonly DesktopApiClient apiClient = new();
    private string? sessionId;

    public MainWindow()
    {
        InitializeComponent();
        ChatItems.ItemsSource = chatMessages;
        LogItems.ItemsSource = logs;
        AddChat("system", "WPF -> HttpClient -> ASP.NET API 구조로 실행됩니다.");
        AddLog("WPF MVP가 시작되었습니다.");
    }

    private async void HealthButton_Click(object sender, RoutedEventArgs e)
    {
        await RunApiActionAsync("상태 확인", async () =>
        {
            var health = await apiClient.GetHealthAsync(ApiBaseUrlBox.Text);
            AddLog($"API={health.Api}, Provider={health.Provider}, Model={health.ModelId}, Endpoint={health.Endpoint}, Installed={health.ModelInstalled}");
        });
    }

    private async void LoadModelsButton_Click(object sender, RoutedEventArgs e)
    {
        await RunApiActionAsync("모델 목록", async () =>
        {
            var models = await apiClient.GetModelsAsync(ApiBaseUrlBox.Text);
            ModelCombo.ItemsSource = models;
            if (models.Count > 0)
            {
                ModelCombo.Text = models[0];
            }

            AddLog($"모델 {models.Count}개를 읽었습니다.");
        });
    }

    private async void NewSessionButton_Click(object sender, RoutedEventArgs e)
    {
        await RunApiActionAsync("새 세션", async () =>
        {
            var session = await apiClient.CreateSessionAsync(ApiBaseUrlBox.Text, "WPF desktop session");
            sessionId = session.SessionId;
            chatMessages.Clear();
            AddChat("system", $"새 세션이 생성되었습니다: {session.SessionId}");
            AddLog($"새 세션: {session.SessionId}");
        });
    }

    private async void SendButton_Click(object sender, RoutedEventArgs e)
    {
        var prompt = PromptBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(prompt))
        {
            AddLog("전송할 메시지가 없습니다.");
            return;
        }

        await RunApiActionAsync("채팅", async () =>
        {
            AddChat("user", prompt);
            var model = string.IsNullOrWhiteSpace(ModelCombo.Text) ? "llama3.1" : ModelCombo.Text.Trim();
            var response = await apiClient.SendChatAsync(ApiBaseUrlBox.Text, sessionId, model, prompt);
            sessionId = response.SessionId;
            AddChat("assistant", response.Message);
            AddLog($"채팅 응답 수신: {response.CreatedAt:HH:mm:ss}");
        });
    }

    private async void ToolButton_Click(object sender, RoutedEventArgs e)
    {
        await RunApiActionAsync("도구 실행", async () =>
        {
            var result = await apiClient.ExecuteToolAsync(ApiBaseUrlBox.Text, "time", "");
            AddLog(result.Success ? $"time={result.Result}" : $"도구 실패: {result.Error}");
        });
    }

    private void SelectFileButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "분석할 파일 선택",
            Filter = "All files (*.*)|*.*"
        };

        if (dialog.ShowDialog(this) == true)
        {
            SelectedFileText.Text = dialog.FileName;
            AddLog($"파일 선택: {dialog.FileName}");
        }
    }

    private void SaveSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        AddLog($"설정 저장: API={ApiBaseUrlBox.Text}, NAS={NasPathBox.Text}");
    }

    private async Task RunApiActionAsync(string name, Func<Task> action)
    {
        try
        {
            SetBusy(true);
            AddLog($"{name} 요청 시작");
            await action();
        }
        catch (Exception ex)
        {
            AddLog($"{name} 실패: {ex.Message}");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void SetBusy(bool busy)
    {
        SendButton.IsEnabled = !busy;
        HealthButton.IsEnabled = !busy;
    }

    private void AddChat(string role, string content)
    {
        chatMessages.Add(new ChatMessageView(role, content));
        ChatScroll.ScrollToEnd();
    }

    private void AddLog(string message)
    {
        logs.Insert(0, $"[{DateTime.Now:HH:mm:ss}] {message}");
    }
}
