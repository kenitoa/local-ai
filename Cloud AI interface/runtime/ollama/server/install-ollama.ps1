param(
    [string]$DownloadUrl = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip",
    [string]$InstallDirectory = (Join-Path $PSScriptRoot "cli"),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$state = Initialize-OllamaLocalEnvironment
$installRoot = [System.IO.Path]::GetFullPath($InstallDirectory)
$targetExe = Join-Path $installRoot "ollama.exe"
$downloadPath = Join-Path $installRoot "ollama-windows-amd64.zip"

Write-Host "Ollama local CLI installation"
Write-Host "InstallDirectory: $installRoot"
Write-Host "HomePath: $($state.HomePath)"
Write-Host "ModelsPath: $($state.ModelsPath)"
Write-Host ""

if ((Test-Path -LiteralPath $targetExe -PathType Leaf) -and -not $Force) {
    Write-Host "Local Ollama CLI already exists: $targetExe" -ForegroundColor Green
    & $targetExe --version
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null

Write-Host "Downloading portable Ollama CLI package..."
Write-Host $DownloadUrl
$curlCommand = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curlCommand) {
    & $curlCommand.Source -L --fail --continue-at - --output $downloadPath $DownloadUrl
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe download failed with exit code $LASTEXITCODE."
    }
}
else {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $downloadPath
}

if (-not (Test-Path -LiteralPath $downloadPath -PathType Leaf) -or
    (Get-Item -LiteralPath $downloadPath).Length -le 0) {
    throw "Download failed or produced an empty file: $downloadPath"
}

Write-Host "Extracting..."
Expand-Archive -LiteralPath $downloadPath -DestinationPath $installRoot -Force

if (-not (Test-Path -LiteralPath $targetExe -PathType Leaf)) {
    $foundExe = Get-ChildItem -LiteralPath $installRoot -Filter "ollama.exe" -Recurse -File |
        Select-Object -First 1

    if (-not $foundExe) {
        throw "ollama.exe was not found after extraction: $installRoot"
    }

    if ($foundExe.FullName -ne $targetExe) {
        Copy-Item -LiteralPath $foundExe.FullName -Destination $targetExe -Force
    }
}

Write-Host ""
Write-Host "Installation check:"
& $targetExe --version
if ($LASTEXITCODE -ne 0) {
    throw "Local ollama.exe exists but version check failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Local CLI is ready. This script does not register Ollama globally or add it to PATH." -ForegroundColor Green
Write-Host "Configured OLLAMA_CLI=$($state.EnvValues['OLLAMA_CLI'])"
Write-Host "Configured OLLAMA_HOME=$($state.EnvValues['OLLAMA_HOME'])"
Write-Host "Configured OLLAMA_MODELS=$($state.EnvValues['OLLAMA_MODELS'])"
