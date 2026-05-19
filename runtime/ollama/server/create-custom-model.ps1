param(
    [string]$ModelName = "local-assistant",
    [string]$ModelfilePath = (Join-Path $PSScriptRoot "Modelfile"),
    [switch]$AutoContext,
    [switch]$RunAfterCreate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$state = Initialize-OllamaLocalEnvironment
$ollamaCli = $state.OllamaCli
if (-not $ollamaCli) {
    throw "Local Ollama CLI was not found. Run install-ollama.ps1 first."
}

if (-not (Test-Path -LiteralPath $ModelfilePath)) {
    throw "Modelfile not found: $ModelfilePath"
}

if ($AutoContext) {
    & "$PSScriptRoot\set-context-length.ps1" -Auto -ModelfilePath $ModelfilePath
}

Write-Host "Creating Ollama custom model"
Write-Host "ModelName: $ModelName"
Write-Host "Modelfile: $ModelfilePath"
Write-Host "OllamaCli: $ollamaCli"
Write-Host "ModelsPath: $($state.ModelsPath)"
Write-Host ""

& $ollamaCli create $ModelName -f $ModelfilePath
if ($LASTEXITCODE -ne 0) {
    throw "ollama create failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Custom model created: $ModelName" -ForegroundColor Green
Write-Host "Use in Semantic Kernel as modelId: `"$ModelName`""

if ($RunAfterCreate) {
    & $ollamaCli run $ModelName
}
