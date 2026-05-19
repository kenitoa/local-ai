param(
  [int]$ApiPort = 5088,
  [int]$OllamaStartupTimeoutSeconds = 45,
  [int]$ApiStartupTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

$PublishRoot = $PSScriptRoot
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PublishRoot "..")).Path
$AppRoot = Join-Path $PublishRoot "app"
$ApiRoot = Join-Path $AppRoot "api"
$WpfRoot = Join-Path $AppRoot "wpf"
$LogRoot = Join-Path $PublishRoot "logs"
$OllamaStartScript = Join-Path $RepoRoot "runtime\ollama\server\start-server.ps1"
$BuildPublishScript = Join-Path $RepoRoot "scripts\build-publish.ps1"
$ApiHealthUrl = "http://localhost:$ApiPort/api/health"

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Write-Step {
  param([string]$Message)
  Write-Host "[local-ai] $Message"
}

function Test-HttpOk {
  param([string]$Url)

  try {
    Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 | Out-Null
    return $true
  }
  catch {
    return $false
  }
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
  $wpfExe = Join-Path $WpfRoot "WpfDesktopMvp.exe"

  if ((Test-Path -LiteralPath $apiExe -PathType Leaf) -and
      (Test-Path -LiteralPath $wpfExe -PathType Leaf)) {
    return
  }

  if (-not (Test-Path -LiteralPath $BuildPublishScript -PathType Leaf)) {
    throw "Publish output is missing and build script was not found: $BuildPublishScript"
  }

  Write-Step "publish output is missing; building API and WPF once"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $BuildPublishScript

  if (-not ((Test-Path -LiteralPath $apiExe -PathType Leaf) -or
            (Test-Path -LiteralPath $apiDll -PathType Leaf))) {
    throw "API publish output was not created in $ApiRoot"
  }

  if (-not (Test-Path -LiteralPath $wpfExe -PathType Leaf)) {
    throw "WPF publish output was not created in $WpfRoot"
  }
}

function Start-Ollama {
  if (-not (Test-Path -LiteralPath $OllamaStartScript -PathType Leaf)) {
    throw "Ollama start script was not found: $OllamaStartScript"
  }

  Write-Step "starting Ollama"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $OllamaStartScript -Background -StartupTimeoutSeconds $OllamaStartupTimeoutSeconds
}

function Start-Api {
  if (Test-HttpOk -Url $ApiHealthUrl) {
    Write-Step "API is already running at $ApiHealthUrl"
    return
  }

  $apiExe = Join-Path $ApiRoot "AspNetAiApi.exe"
  $apiDll = Join-Path $ApiRoot "AspNetAiApi.dll"
  $outLog = Join-Path $LogRoot "api.stdout.log"
  $errLog = Join-Path $LogRoot "api.stderr.log"
  Remove-Item -LiteralPath $outLog, $errLog -Force -ErrorAction SilentlyContinue

  Write-Step "starting ASP.NET API on port $ApiPort"
  if (Test-Path -LiteralPath $apiExe -PathType Leaf) {
    Start-Process -FilePath $apiExe `
      -WorkingDirectory $ApiRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput $outLog `
      -RedirectStandardError $errLog | Out-Null
  }
  elseif (Test-Path -LiteralPath $apiDll -PathType Leaf) {
    Start-Process -FilePath "dotnet" `
      -ArgumentList "`"$apiDll`"" `
      -WorkingDirectory $ApiRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput $outLog `
      -RedirectStandardError $errLog | Out-Null
  }
  else {
    throw "API publish output was not found in $ApiRoot"
  }

  Wait-HttpOk -Url $ApiHealthUrl -TimeoutSeconds $ApiStartupTimeoutSeconds -Name "ASP.NET API"
}

function Start-Wpf {
  $wpfExe = Join-Path $WpfRoot "WpfDesktopMvp.exe"
  if (-not (Test-Path -LiteralPath $wpfExe -PathType Leaf)) {
    throw "WPF publish output was not found: $wpfExe"
  }

  Write-Step "opening WPF desktop UI"
  Start-Process -FilePath $wpfExe -WorkingDirectory $WpfRoot | Out-Null
}

Push-Location $RepoRoot
try {
  Ensure-PublishedApps
  Start-Ollama
  Start-Api
  Start-Wpf
  Write-Step "ready"
}
finally {
  Pop-Location
}
