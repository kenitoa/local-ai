param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LibraryUrl = "https://ollama.com/library"
$CatalogPath = Join-Path $PSScriptRoot "models.ollama-library.txt"

Write-Host "Fetching current Ollama library catalog..."
Write-Host $LibraryUrl

$response = Invoke-WebRequest -Uri $LibraryUrl -UseBasicParsing -TimeoutSec 60
$html = [string]$response.Content

$matches = [regex]::Matches($html, 'href="/library/([A-Za-z0-9][A-Za-z0-9._-]*)"')
$models = $matches |
    ForEach-Object { $_.Groups[1].Value } |
    Sort-Object -Unique

if ($models.Count -eq 0) {
    throw "No Ollama library model names were found at $LibraryUrl"
}

$models | Set-Content -LiteralPath $CatalogPath -Encoding UTF8

Write-Host "Catalog saved: $CatalogPath"
Write-Host "Model families found: $($models.Count)"
Write-Host ""

& "$PSScriptRoot\pull-models.ps1" -ModelFile $CatalogPath -ContinueOnError -DryRun:$DryRun
