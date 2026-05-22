param(
    [switch]$Background,
    [int]$StartupTimeoutSeconds = 30,
    [switch]$AllowPathFallback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$state = Initialize-OllamaLocalEnvironment -AllowPathFallback:$AllowPathFallback
$HostBinding = $state.HostBinding
$Endpoint = $state.Endpoint
$TagsUrl = $state.TagsUrl
$ollamaCli = $state.OllamaCli

function Test-OllamaServer {
    try {
        Invoke-RestMethod -Uri $TagsUrl -Method Get -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

if (-not $ollamaCli) {
    throw "Local Ollama CLI was not found. Run install-ollama.ps1 first. PATH fallback is intentionally disabled unless -AllowPathFallback is used."
}

if (Test-OllamaServer) {
    Write-Host "Ollama server is already running: $Endpoint" -ForegroundColor Green
    Write-Host "OLLAMA_CLI=$ollamaCli"
    Write-Host "OLLAMA_HOST=$HostBinding"
    if ($state.HomePath) {
        Write-Host "OLLAMA_HOME=$($state.HomePath)"
    }
    if ($env:OLLAMA_MODELS) {
        Write-Host "OLLAMA_MODELS=$env:OLLAMA_MODELS"
    }
    if ($env:OLLAMA_CONTEXT_LENGTH) {
        Write-Host "OLLAMA_CONTEXT_LENGTH=$env:OLLAMA_CONTEXT_LENGTH"
    }
    exit 0
}

if (-not $Background) {
    Write-Host "Starting Ollama server in this PowerShell session..."
    Write-Host "Endpoint: $Endpoint"
    Write-Host "OLLAMA_CLI=$ollamaCli"
    Write-Host "OLLAMA_HOST=$HostBinding"
    if ($state.HomePath) {
        Write-Host "OLLAMA_HOME=$($state.HomePath)"
    }
    if ($env:OLLAMA_MODELS) {
        Write-Host "OLLAMA_MODELS=$env:OLLAMA_MODELS"
    }
    if ($env:OLLAMA_CONTEXT_LENGTH) {
        Write-Host "OLLAMA_CONTEXT_LENGTH=$env:OLLAMA_CONTEXT_LENGTH"
    }
    Write-Host "Stop with Ctrl+C."
    & $ollamaCli serve
    exit $LASTEXITCODE
}

Write-Host "Starting Ollama server in the background..."
Write-Host "OLLAMA_CLI=$ollamaCli"
Write-Host "OLLAMA_HOST=$HostBinding"
if ($state.HomePath) {
    Write-Host "OLLAMA_HOME=$($state.HomePath)"
}
if ($env:OLLAMA_MODELS) {
    Write-Host "OLLAMA_MODELS=$env:OLLAMA_MODELS"
}
if ($env:OLLAMA_CONTEXT_LENGTH) {
    Write-Host "OLLAMA_CONTEXT_LENGTH=$env:OLLAMA_CONTEXT_LENGTH"
}
$stdoutLog = Join-Path $PSScriptRoot "ollama-serve.stdout.log"
$stderrLog = Join-Path $PSScriptRoot "ollama-serve.stderr.log"
Remove-Item -LiteralPath $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue
Start-Process `
    -FilePath $ollamaCli `
    -ArgumentList "serve" `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-OllamaServer) {
        Write-Host "Ollama server is running: $Endpoint" -ForegroundColor Green
        exit 0
    }

    Start-Sleep -Seconds 1
}

throw "Ollama server did not become reachable within $StartupTimeoutSeconds seconds."
