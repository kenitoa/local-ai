param(
  [int]$ApiPort = 5088,
  [int]$OllamaStartupTimeoutSeconds = 45,
  [int]$ApiStartupTimeoutSeconds = 45,
  [switch]$WaitForOllama,
  [switch]$NoWeb,
  [switch]$LaunchWeb,
  [switch]$LaunchWpf,
  [switch]$NoWpf,
  [switch]$RefreshPublish
)

$ErrorActionPreference = "Stop"

$PublishRoot = $PSScriptRoot
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PublishRoot "..")).Path
$SourceRoot = Join-Path $RepoRoot "Cloud AI interface"
if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
  $SourceRoot = $RepoRoot
}
$AppRoot = Join-Path $PublishRoot "app"
$ApiRoot = Join-Path $AppRoot "api"
$WpfRoot = Join-Path $AppRoot "wpf"
$LogRoot = Join-Path $PublishRoot "logs"
$WebSource = Join-Path $SourceRoot "apps\web"
$WebOut = Join-Path $ApiRoot "wwwroot"
$OllamaStartScript = Join-Path $SourceRoot "runtime\ollama\server\start-server.ps1"
$BuildPublishScript = Join-Path $SourceRoot "scripts\build-publish.ps1"
$ApiReadyUrl = "http://localhost:$ApiPort/api/ready"
$ApiHealthUrl = "http://localhost:$ApiPort/api/health"
$ApiCloudInterfaceUrl = "http://localhost:$ApiPort/api/cloud-ai/interface"
$ApiMarketUrl = "http://localhost:$ApiPort/api/market/models"
$WebUrl = "http://localhost:$ApiPort/"
$OllamaTagsUrl = "http://localhost:11434/api/tags"

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Write-Step {
  param([string]$Message)
  Write-Host "[local-ai] $Message"
}

function Test-HttpOk {
  param(
    [string]$Url,
    [int]$TimeoutSeconds = 6
  )

  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Get -TimeoutSec $TimeoutSeconds -ErrorAction Stop
    return ($response.StatusCode -ge 200) -and ($response.StatusCode -lt 300)
  }
  catch {
    return $false
  }
}

function Test-ApiCompatible {
  return (Test-HttpOk -Url $ApiReadyUrl) -and
    (Test-HttpOk -Url $ApiHealthUrl) -and
    (Test-HttpOk -Url $ApiCloudInterfaceUrl) -and
    (Test-HttpOk -Url $ApiMarketUrl)
}

function Get-ListeningProcess {
  try {
    $connection = Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction Stop |
      Select-Object -First 1
    if (-not $connection) {
      return $null
    }

    return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
  }
  catch {
    return $null
  }
}

function Stop-IncompatibleRepoApi {
  $processes = @(Get-Process AspNetAiApi -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Path -and (
        $_.Path.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $_.Path.StartsWith($SourceRoot, [StringComparison]::OrdinalIgnoreCase)
      )
    })

  if ($processes.Count -eq 0) {
    $process = Get-ListeningProcess
    if (-not $process) {
      return
    }

    $processPath = $process.Path
    if (-not $processPath -or (
        -not $processPath.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -and
        -not $processPath.StartsWith($SourceRoot, [StringComparison]::OrdinalIgnoreCase))) {
      throw "Port $ApiPort is already used by a non-local-ai process: $($process.ProcessName) ($($process.Id))"
    }

    $processes = @($process)
  }

  foreach ($process in $processes) {
    Write-Step "stopping incompatible API process $($process.ProcessName) ($($process.Id))"
    Stop-Process -Id $process.Id -Force
  }

  Start-Sleep -Seconds 1
}

function Wait-HttpOk {
  param(
    [string]$Url,
    [int]$TimeoutSeconds,
    [string]$Name
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-HttpOk -Url $Url) {
      return
    }

    Start-Sleep -Milliseconds 500
  }

  throw "$Name did not become reachable at $Url within $TimeoutSeconds seconds."
}

function Ensure-PublishedApps {
  $apiExe = Join-Path $ApiRoot "AspNetAiApi.exe"
  $apiDll = Join-Path $ApiRoot "AspNetAiApi.dll"
  $apiOutput = @($apiExe, $apiDll) |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

  if ($apiOutput -and -not $RefreshPublish) {
    Write-Step "using existing publish output at $ApiRoot"
    Sync-WebAssets
    return
  }

  if (-not (Test-Path -LiteralPath $BuildPublishScript -PathType Leaf)) {
    throw "Publish output is missing and build script was not found: $BuildPublishScript"
  }

  Stop-IncompatibleRepoApi
  if ($RefreshPublish) {
    Write-Step "refreshing publish output by request"
  }
  else {
    Write-Step "publish output is missing; building API and desktop UI once"
  }
  & powershell -NoProfile -ExecutionPolicy Bypass -File $BuildPublishScript -IncludeWpf

  if (-not ((Test-Path -LiteralPath $apiExe -PathType Leaf) -or
            (Test-Path -LiteralPath $apiDll -PathType Leaf))) {
    throw "API publish output was not created in $ApiRoot"
  }

  Sync-WebAssets
}

function Sync-WebAssets {
  $webIndex = Join-Path $WebSource "index.html"
  if (-not (Test-Path -LiteralPath $webIndex -PathType Leaf)) {
    if (Test-Path -LiteralPath (Join-Path $WebOut "index.html") -PathType Leaf) {
      Write-Step "web source was not found; using existing published web assets"
      return
    }

    throw "Web UI source was not found and published web assets are missing: $WebSource"
  }

  $sourceFiles = @(
    (Join-Path $WebSource "index.html"),
    (Join-Path $WebSource "src")
  ) | ForEach-Object {
    Get-ChildItem -LiteralPath $_ -Recurse -File
  }
  $destinationIndex = Join-Path $WebOut "index.html"
  if ((Test-Path -LiteralPath $destinationIndex -PathType Leaf) -and $sourceFiles.Count -gt 0) {
    $newestSource = ($sourceFiles | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc
    $newestDestination = (Get-ChildItem -LiteralPath $WebOut -Recurse -File |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1).LastWriteTimeUtc

    if ($newestDestination -ge $newestSource) {
      return
    }
  }

  if (Test-Path -LiteralPath $WebOut) {
    Remove-Item -LiteralPath $WebOut -Recurse -Force
  }

  New-Item -ItemType Directory -Force -Path $WebOut | Out-Null
  Copy-Item -LiteralPath (Join-Path $WebSource "index.html") -Destination $WebOut -Force
  Copy-Item -LiteralPath (Join-Path $WebSource "src") -Destination $WebOut -Recurse -Force
}

function Start-Ollama {
  if (-not (Test-Path -LiteralPath $OllamaStartScript -PathType Leaf)) {
    Write-Step "Ollama start script was not found; skipping automatic Ollama startup"
    return
  }

  if (Test-HttpOk -Url $OllamaTagsUrl -TimeoutSeconds 2) {
    Write-Step "Ollama is already running at $OllamaTagsUrl"
    return
  }

  $startupTimeout = if ($WaitForOllama) { $OllamaStartupTimeoutSeconds } else { 3 }
  $mode = if ($WaitForOllama) { "waiting up to $startupTimeout seconds" } else { "background, fast startup path" }
  Write-Step "starting Ollama ($mode)"
  $ollamaLog = Join-Path $LogRoot "ollama.startup.log"
  $ollamaErrLog = Join-Path $LogRoot "ollama.startup.stderr.log"
  Remove-Item -LiteralPath $ollamaLog, $ollamaErrLog -Force -ErrorAction SilentlyContinue

  $arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$OllamaStartScript`"",
    "-Background",
    "-StartupTimeoutSeconds", "$startupTimeout"
  )

  Start-Process -FilePath "powershell" `
    -ArgumentList $arguments `
    -WindowStyle Hidden `
    -RedirectStandardOutput $ollamaLog `
    -RedirectStandardError $ollamaErrLog | Out-Null

  if ($WaitForOllama) {
    Wait-HttpOk -Url $OllamaTagsUrl -TimeoutSeconds $OllamaStartupTimeoutSeconds -Name "Ollama"
    Write-Step "Ollama is running at $OllamaTagsUrl"
    return
  }

  Start-Sleep -Seconds 1
  if (-not (Test-HttpOk -Url $OllamaTagsUrl -TimeoutSeconds 2)) {
    Write-Step "Ollama is still starting in the background; details: $ollamaLog"
  }
}

function Start-Api {
  if (Test-ApiCompatible) {
    Write-Step "API is already running at $ApiHealthUrl"
    return
  }

  if (Test-HttpOk -Url $ApiHealthUrl) {
    Write-Step "API is reachable but missing required Cloud AI endpoints"
    Stop-IncompatibleRepoApi
  }

  $apiCandidates = @(
    (Join-Path $ApiRoot "AspNetAiApi.exe"),
    (Join-Path $ApiRoot "AspNetAiApi.dll"),
    (Join-Path $SourceRoot "ui\api\bin\Release\net9.0\AspNetAiApi.exe"),
    (Join-Path $SourceRoot "ui\api\bin\Release\net9.0\AspNetAiApi.dll"),
    (Join-Path $SourceRoot "ui\api\bin\Debug\net9.0\AspNetAiApi.exe"),
    (Join-Path $SourceRoot "ui\api\bin\Debug\net9.0\AspNetAiApi.dll")
  )
  $apiPath = $apiCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
  $outLog = Join-Path $LogRoot "api.stdout.log"
  $errLog = Join-Path $LogRoot "api.stderr.log"
  Remove-Item -LiteralPath $outLog, $errLog -Force -ErrorAction SilentlyContinue

  Write-Step "starting ASP.NET API on port $ApiPort"
  if (-not $apiPath) {
    throw "API output was not found in publish or ui/api/bin"
  }

  $apiWorkingDirectory = Split-Path -Parent $apiPath
  $previousLocalAiApiUrls = $env:LOCAL_AI_API_URLS
  $previousAspNetCoreUrls = $env:ASPNETCORE_URLS
  $apiProcess = $null
  $env:LOCAL_AI_API_URLS = "http://localhost:$ApiPort"
  try {
    if ([IO.Path]::GetExtension($apiPath).Equals(".exe", [StringComparison]::OrdinalIgnoreCase)) {
      $apiProcess = Start-Process -FilePath $apiPath `
        -WorkingDirectory $apiWorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru
    }
    else {
      $apiProcess = Start-Process -FilePath "dotnet" `
        -ArgumentList "`"$apiPath`"" `
        -WorkingDirectory $apiWorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru
    }
  }
  finally {
    if ($null -eq $previousLocalAiApiUrls) {
      Remove-Item Env:LOCAL_AI_API_URLS -ErrorAction SilentlyContinue
    }
    else {
      $env:LOCAL_AI_API_URLS = $previousLocalAiApiUrls
    }

    if ($null -eq $previousAspNetCoreUrls) {
      Remove-Item Env:ASPNETCORE_URLS -ErrorAction SilentlyContinue
    }
    else {
      $env:ASPNETCORE_URLS = $previousAspNetCoreUrls
    }
  }

  Wait-HttpOk -Url $ApiReadyUrl -TimeoutSeconds $ApiStartupTimeoutSeconds -Name "ASP.NET API"
  if ($apiProcess -and $apiProcess.HasExited) {
    throw "ASP.NET API exited during startup. See $outLog and $errLog."
  }

  if (-not (Test-ApiCompatible)) {
    throw "ASP.NET API started, but required Cloud AI endpoints are not reachable."
  }

  Start-Sleep -Seconds 1
  if ($apiProcess -and $apiProcess.HasExited) {
    throw "ASP.NET API exited after startup checks. See $outLog and $errLog."
  }
}

function Start-Wpf {
  $candidatePaths = @(
    (Join-Path $WpfRoot "WpfDesktopMvp.exe"),
    (Join-Path $SourceRoot "ui\wpf\bin\Release\net9.0-windows\WpfDesktopMvp.exe"),
    (Join-Path $SourceRoot "ui\wpf\bin\Debug\net9.0-windows\WpfDesktopMvp.exe")
  )

  $wpfExe = $candidatePaths |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

  if (-not $wpfExe) {
    Write-Step "WPF desktop output was not found; skipping desktop UI"
    return
  }

  $workingDirectory = Split-Path -Parent $wpfExe
  Write-Step "opening Windows desktop UI"
  Start-Process -FilePath $wpfExe -WorkingDirectory $workingDirectory | Out-Null
}

function Start-Web {
  $webIndex = Join-Path $WebOut "index.html"
  if (Test-Path -LiteralPath $webIndex -PathType Leaf) {
    Write-Step "opening Web UI at $webIndex"
    Start-Process -FilePath $webIndex | Out-Null
    return
  }

  Write-Step "opening Web UI at $WebUrl"
  Start-Process -FilePath $WebUrl | Out-Null
}

Push-Location $SourceRoot
try {
  Ensure-PublishedApps
  Start-Ollama
  Start-Api
  if (-not $NoWpf) {
    Start-Wpf
  }
  elseif ($LaunchWpf) {
    Start-Wpf
  }
  if ($LaunchWeb -and -not $NoWeb) {
    Start-Web
  }
  Write-Step "ready"
}
finally {
  Pop-Location
}
