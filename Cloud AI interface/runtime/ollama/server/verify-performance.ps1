param(
    [string]$Model = "local-assistant",
    [int]$ConcurrentRequests = 2,
    [int]$TimeoutSeconds = 180,
    [int]$StartupTimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$originalHome = [Environment]::GetEnvironmentVariable("HOME", "Process")
$originalUserProfile = [Environment]::GetEnvironmentVariable("USERPROFILE", "Process")
$state = Initialize-OllamaLocalEnvironment
if (-not $state.OllamaCli) {
    throw "Local Ollama CLI was not found. Run install-ollama.ps1 first."
}

$startedHere = $false
$serverProcess = $null

function Test-LocalOllama {
    try {
        Invoke-RestMethod -Uri $state.TagsUrl -Method Get -TimeoutSec 3 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

try {
    if (-not (Test-LocalOllama)) {
        $serverProcess = Start-Process `
            -FilePath $state.OllamaCli `
            -ArgumentList "serve" `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $PSScriptRoot "ollama-serve.stdout.log") `
            -RedirectStandardError (Join-Path $PSScriptRoot "ollama-serve.stderr.log") `
            -PassThru
        $startedHere = $true

        $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
        while ((Get-Date) -lt $deadline) {
            if (Test-LocalOllama) {
                break
            }
            Start-Sleep -Seconds 1
        }
    }

    if (-not (Test-LocalOllama)) {
        throw "Ollama server is not reachable at $($state.TagsUrl)."
    }

    if ($originalHome) {
        [Environment]::SetEnvironmentVariable("HOME", $originalHome, "Process")
    }
    if ($originalUserProfile) {
        [Environment]::SetEnvironmentVariable("USERPROFILE", $originalUserProfile, "Process")
    }

    & "$PSScriptRoot\measure-hardware.ps1"
    & "$PSScriptRoot\benchmark-server.ps1" `
        -Model $Model `
        -Endpoint $state.Endpoint `
        -ConcurrentRequests $ConcurrentRequests `
        -TimeoutSeconds $TimeoutSeconds
}
finally {
    if ($startedHere -and $serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
}
