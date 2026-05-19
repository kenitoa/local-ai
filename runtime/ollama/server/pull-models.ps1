param(
    [string]$ModelFile,
    [string[]]$Models,
    [switch]$DryRun,
    [switch]$ContinueOnError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\ollama-env.ps1"

$state = Initialize-OllamaLocalEnvironment
$ollamaCli = $state.OllamaCli
$ResultsPath = Join-Path $PSScriptRoot "pull-results.json"

function Get-ModelNames {
    if ($Models -and $Models.Count -gt 0) {
        return $Models
    }

    if (-not [string]::IsNullOrWhiteSpace($ModelFile)) {
        if (-not (Test-Path -LiteralPath $ModelFile)) {
            throw "Model file not found: $ModelFile"
        }

        return Get-Content -LiteralPath $ModelFile |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -and -not $_.StartsWith("#") }
    }

    throw "Provide -ModelFile or -Models."
}

function Get-InstalledModelNames {
    $installed = @()

    try {
        $listOutput = & $ollamaCli list 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $listOutput) {
            return $installed
        }

        $installed = $listOutput |
            Select-Object -Skip 1 |
            ForEach-Object {
                $parts = $_ -split "\s+"
                if ($parts.Count -gt 0) {
                    $parts[0]
                }
            } |
            Where-Object { $_ }
    }
    catch {
        return @()
    }

    return $installed
}

function Test-ModelInstalled {
    param(
        [string]$ModelName,
        [string[]]$InstalledModels
    )

    $latestName = "$ModelName`:latest"
    return ($InstalledModels -contains $ModelName) -or ($InstalledModels -contains $latestName)
}

if (-not $ollamaCli) {
    if ($DryRun) {
        Write-Host "Dry run: local Ollama CLI was not found, so installed-model checks will be skipped." -ForegroundColor Yellow
    }
    else {
        throw "Local Ollama CLI was not found. Run install-ollama.ps1 first."
    }
}

$modelNames = @(Get-ModelNames | Sort-Object -Unique)
if ($modelNames.Count -eq 0) {
    throw "No models to pull."
}

Write-Host "Model pull count: $($modelNames.Count)"
Write-Host "Results: $ResultsPath"
Write-Host "OllamaCli: $ollamaCli"
Write-Host "ModelsPath: $($state.ModelsPath)"
Write-Host ""

$installedModels = if ($ollamaCli) { @(Get-InstalledModelNames) } else { @() }
$results = New-Object System.Collections.Generic.List[object]

foreach ($model in $modelNames) {
    $startedAt = Get-Date
    Write-Host "==> $model"

    if (Test-ModelInstalled -ModelName $model -InstalledModels $installedModels) {
        Write-Host "Already installed. Skipping." -ForegroundColor Yellow
        $results.Add([ordered]@{
            model = $model
            status = "skipped"
            startedAt = $startedAt.ToString("o")
            finishedAt = (Get-Date).ToString("o")
            exitCode = 0
        })
        continue
    }

    if ($DryRun) {
        Write-Host "Dry run: $ollamaCli pull $model"
        $results.Add([ordered]@{
            model = $model
            status = "dry-run"
            startedAt = $startedAt.ToString("o")
            finishedAt = (Get-Date).ToString("o")
            exitCode = 0
        })
        continue
    }

    & $ollamaCli pull $model
    $exitCode = $LASTEXITCODE
    $status = if ($exitCode -eq 0) { "ok" } else { "failed" }

    $results.Add([ordered]@{
        model = $model
        status = $status
        startedAt = $startedAt.ToString("o")
        finishedAt = (Get-Date).ToString("o")
        exitCode = $exitCode
    })

    $results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultsPath -Encoding UTF8

    if ($exitCode -ne 0 -and -not $ContinueOnError) {
        throw "ollama pull failed for model '$model' with exit code $exitCode."
    }

    $installedModels = @(Get-InstalledModelNames)
    Write-Host ""
}

$results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultsPath -Encoding UTF8
Write-Host "Done."
