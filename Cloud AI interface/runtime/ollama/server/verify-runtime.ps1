param(
    [string]$ModelId = "local-assistant",
    [string]$SelectedModelFile = (Join-Path $PSScriptRoot "models.selected.txt"),
    [switch]$PullSelectedModels,
    [switch]$CreateCustomModel,
    [switch]$SkipBuild,
    [int]$StartupTimeoutSeconds = 60
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$state = Initialize-OllamaLocalEnvironment
if (-not $state.OllamaCli) {
    throw "Local Ollama CLI was not found. Run install-ollama.ps1 first."
}

$startedHere = $false
$serverProcess = $null
$stdoutLog = Join-Path $PSScriptRoot "ollama-serve.stdout.log"
$stderrLog = Join-Path $PSScriptRoot "ollama-serve.stderr.log"

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
        Remove-Item -LiteralPath $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue
        $serverProcess = Start-Process `
            -FilePath $state.OllamaCli `
            -ArgumentList "serve" `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog `
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
        $stderr = Get-Content -Raw -LiteralPath $stderrLog -ErrorAction SilentlyContinue
        throw "Ollama server is not reachable at $($state.TagsUrl). $stderr"
    }

    Write-Host "Ollama server reachable: $($state.Endpoint)" -ForegroundColor Green
    Write-Host "OllamaCli: $($state.OllamaCli)"
    Write-Host "OllamaHome: $($state.HomePath)"
    Write-Host "OllamaModels: $($state.ModelsPath)"
    Write-Host ""

    if ($PullSelectedModels) {
        & "$PSScriptRoot\pull-models.ps1" -ModelFile $SelectedModelFile
    }

    if ($CreateCustomModel) {
        & "$PSScriptRoot\create-custom-model.ps1" -ModelName $ModelId
    }

    & "$PSScriptRoot\test-api.ps1" -Model $ModelId -EmbedModel "nomic-embed-text" -Endpoint $state.Endpoint

    if ($SkipBuild) {
        & "$PSScriptRoot\validate-final-implementation.ps1" -ModelId $ModelId -Endpoint $state.Endpoint -SkipBuild
    }
    else {
        & "$PSScriptRoot\validate-final-implementation.ps1" -ModelId $ModelId -Endpoint $state.Endpoint
    }
}
finally {
    if ($startedHere -and $serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
}
