param([switch]$AllowPathFallback)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$state = Initialize-OllamaLocalEnvironment -AllowPathFallback:$AllowPathFallback
$Endpoint = $state.Endpoint
$TagsUrl = $state.TagsUrl
$ollamaCli = $state.OllamaCli

Write-Host "Ollama Local Server check"
Write-Host "Endpoint: $Endpoint"
Write-Host "HomePath: $($state.HomePath)"
Write-Host "ModelsPath: $($state.ModelsPath)"
Write-Host ""

if (-not $ollamaCli) {
    Write-Host "Local Ollama CLI was not found." -ForegroundColor Red
    Write-Host "Run: .\install-ollama.ps1"
    exit 1
}

Write-Host "CLI: $ollamaCli"
& $ollamaCli --version
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri $TagsUrl -Method Get -TimeoutSec 5
}
catch {
    Write-Host "Server is not reachable at $TagsUrl" -ForegroundColor Red
    Write-Host "Start with: .\start-server.ps1 -Background"
    Write-Host "Manual check: curl $TagsUrl"
    exit 2
}

Write-Host "Server: reachable" -ForegroundColor Green
Write-Host "Installed models:"

if ($null -eq $response.models -or $response.models.Count -eq 0) {
    Write-Host "- no models installed"
    Write-Host "Example: .\pull-models.ps1 -Models llama3.1"
    exit 0
}

foreach ($model in $response.models) {
    if ($model.name) {
        Write-Host "- $($model.name)"
    }
}
