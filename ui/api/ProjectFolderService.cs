namespace AspNetAiApi;

using System.Text.Json;

public sealed class ProjectFolderService
{
    private const string ChatsDirectoryName = "chats";

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly string _repoRoot;
    private readonly string _projectRoot;

    public ProjectFolderService(IWebHostEnvironment environment)
    {
        _repoRoot = FindRepoRoot(environment.ContentRootPath);
        _projectRoot = Path.Combine(_repoRoot, "data", "projects");
        Directory.CreateDirectory(_projectRoot);
    }

    public IReadOnlyList<ProjectFolderDto> List()
    {
        Directory.CreateDirectory(_projectRoot);

        return Directory.GetDirectories(_projectRoot)
            .Select(path =>
            {
                var directory = new DirectoryInfo(path);
                return ToDto(directory);
            })
            .OrderBy(project => project.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    public ProjectFolderDto Create(string name)
    {
        var path = ResolveProjectPath(name);
        if (Directory.Exists(path))
        {
            throw new InvalidOperationException("이미 같은 이름의 프로젝트 폴더가 있습니다.");
        }

        Directory.CreateDirectory(path);
        Directory.CreateDirectory(Path.Combine(path, ChatsDirectoryName));

        return ToDto(new DirectoryInfo(path));
    }

    public ProjectFolderDto Rename(string currentName, string newName)
    {
        var currentPath = ResolveProjectPath(currentName);
        if (!Directory.Exists(currentPath))
        {
            throw new DirectoryNotFoundException("프로젝트 폴더를 찾을 수 없습니다.");
        }

        var newPath = ResolveProjectPath(newName);
        if (currentPath.Equals(newPath, StringComparison.OrdinalIgnoreCase))
        {
            return ToDto(new DirectoryInfo(currentPath));
        }

        if (Directory.Exists(newPath))
        {
            throw new InvalidOperationException("이미 같은 이름의 프로젝트 폴더가 있습니다.");
        }

        try
        {
            Directory.Move(currentPath, newPath);
        }
        catch (IOException)
        {
            CopyDirectory(currentPath, newPath);
            Directory.Delete(currentPath, recursive: true);
        }
        catch (UnauthorizedAccessException)
        {
            CopyDirectory(currentPath, newPath);
            Directory.Delete(currentPath, recursive: true);
        }

        return ToDto(new DirectoryInfo(newPath));
    }

    public ProjectChatDto CreateChat(string projectName, string? title)
    {
        var projectPath = ResolveProjectPath(projectName);
        if (!Directory.Exists(projectPath))
        {
            throw new DirectoryNotFoundException("프로젝트 폴더를 찾을 수 없습니다.");
        }

        var chatsPath = Path.Combine(projectPath, ChatsDirectoryName);
        Directory.CreateDirectory(chatsPath);

        var now = DateTimeOffset.UtcNow;
        var chat = new ProjectChatDto(
            Guid.NewGuid().ToString("N"),
            NormalizeChatTitle(title, ListChats(projectPath).Count + 1),
            Guid.NewGuid().ToString("N"),
            now,
            now);

        var filePath = ResolveChatFilePath(projectPath, chat.Id);
        File.WriteAllText(filePath, JsonSerializer.Serialize(chat, JsonOptions));

        return chat;
    }

    public bool Delete(string name)
    {
        var path = ResolveProjectPath(name);
        if (!Directory.Exists(path))
        {
            return false;
        }

        Directory.Delete(path, recursive: true);
        return true;
    }

    private string ResolveProjectPath(string name)
    {
        var cleanName = NormalizeName(name);
        var path = Path.GetFullPath(Path.Combine(_projectRoot, cleanName));

        if (!IsSameOrChildPath(path, _projectRoot))
        {
            throw new ArgumentException("프로젝트 폴더 경로가 허용된 범위를 벗어났습니다.");
        }

        return path;
    }

    private ProjectFolderDto ToDto(DirectoryInfo directory)
    {
        return new ProjectFolderDto(
            directory.Name,
            Path.GetRelativePath(_repoRoot, directory.FullName),
            directory.CreationTimeUtc,
            directory.LastWriteTimeUtc,
            ListChats(directory.FullName));
    }

    private string ResolveChatFilePath(string projectPath, string chatId)
    {
        var chatsPath = Path.GetFullPath(Path.Combine(projectPath, ChatsDirectoryName));
        Directory.CreateDirectory(chatsPath);

        var fileName = $"{NormalizeChatId(chatId)}.json";
        var path = Path.GetFullPath(Path.Combine(chatsPath, fileName));

        if (!IsSameOrChildPath(path, chatsPath))
        {
            throw new ArgumentException("채팅 파일 경로가 허용된 범위를 벗어났습니다.");
        }

        return path;
    }

    private static IReadOnlyList<ProjectChatDto> ListChats(string projectPath)
    {
        var chatsPath = Path.Combine(projectPath, ChatsDirectoryName);
        if (!Directory.Exists(chatsPath))
        {
            return [];
        }

        return Directory.GetFiles(chatsPath, "*.json")
            .Select(ReadChat)
            .Where(chat => chat is not null)
            .Select(chat => chat!)
            .OrderByDescending(chat => chat.ModifiedAt)
            .ToList();
    }

    private static ProjectChatDto? ReadChat(string path)
    {
        try
        {
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<ProjectChatDto>(json, JsonOptions);
        }
        catch
        {
            return null;
        }
    }

    private static void CopyDirectory(string sourcePath, string targetPath)
    {
        Directory.CreateDirectory(targetPath);

        foreach (var file in Directory.GetFiles(sourcePath))
        {
            File.Copy(file, Path.Combine(targetPath, Path.GetFileName(file)), overwrite: false);
        }

        foreach (var directory in Directory.GetDirectories(sourcePath))
        {
            CopyDirectory(directory, Path.Combine(targetPath, Path.GetFileName(directory)));
        }
    }

    private static string NormalizeName(string name)
    {
        var cleanName = (name ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanName))
        {
            throw new ArgumentException("프로젝트 폴더 이름을 입력해주세요.");
        }

        if (cleanName is "." or "..")
        {
            throw new ArgumentException("사용할 수 없는 프로젝트 폴더 이름입니다.");
        }

        if (cleanName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            throw new ArgumentException("프로젝트 폴더 이름에 사용할 수 없는 문자가 있습니다.");
        }

        return cleanName;
    }

    private static string NormalizeChatTitle(string? title, int index)
    {
        var cleanTitle = (title ?? string.Empty).Trim();
        return string.IsNullOrWhiteSpace(cleanTitle)
            ? $"새 채팅 {index}"
            : cleanTitle;
    }

    private static string NormalizeChatId(string chatId)
    {
        var cleanId = (chatId ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(cleanId) || cleanId.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            throw new ArgumentException("사용할 수 없는 채팅 ID입니다.");
        }

        return cleanId;
    }

    private static string FindRepoRoot(string startPath)
    {
        var current = new DirectoryInfo(startPath);
        while (current is not null)
        {
            var hasGit = Directory.Exists(Path.Combine(current.FullName, ".git"));
            var hasAppFolders =
                Directory.Exists(Path.Combine(current.FullName, "apps")) &&
                Directory.Exists(Path.Combine(current.FullName, "ui"));

            if (hasGit || hasAppFolders)
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        return Directory.GetCurrentDirectory();
    }

    private static bool IsSameOrChildPath(string path, string parent)
    {
        var normalizedPath = Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
        var normalizedParent = Path.TrimEndingDirectorySeparator(Path.GetFullPath(parent));

        return normalizedPath.Equals(normalizedParent, StringComparison.OrdinalIgnoreCase) ||
            normalizedPath.StartsWith(normalizedParent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }
}
