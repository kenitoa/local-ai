param(
    [int]$NumCtx,
    [switch]$Auto,
    [string]$EnvPath,
    [string]$ModelfilePath = (Join-Path $PSScriptRoot "Modelfile")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $current = $PSScriptRoot
    while ($current) {
        if (Test-Path -LiteralPath (Join-Path $current ".git")) {
            return $current
        }

        $parent = Split-Path -Parent $current
        if ($parent -eq $current) {
            break
        }

        $current = $parent
    }

    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
}

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Value
    )

    $lines = @()
    if (Test-Path -LiteralPath $Path) {
        $lines = @(Get-Content -Encoding UTF8 -LiteralPath $Path)
    }

    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=") {
            $found = $true
            "$Name=$Value"
        }
        else {
            $line
        }
    }

    if (-not $found) {
        $updated += "$Name=$Value"
    }

    $updated | Set-Content -LiteralPath $Path -Encoding UTF8
}

if (-not $EnvPath) {
    $EnvPath = Join-Path (Get-RepoRoot) ".env"
}

if ($Auto) {
    $hardwareJson = & "$PSScriptRoot\measure-hardware.ps1" -Json | Out-String
    $hardware = $hardwareJson | ConvertFrom-Json
    $NumCtx = [int]$hardware.recommendation.numCtx
    Write-Host "Auto selected num_ctx=$NumCtx"
    Write-Host $hardware.recommendation.reason
}

if ($NumCtx -le 0) {
    throw "Provide -NumCtx or use -Auto."
}

Set-DotEnvValue -Path $EnvPath -Name "OLLAMA_CONTEXT_LENGTH" -Value ([string]$NumCtx)

if (-not (Test-Path -LiteralPath $ModelfilePath)) {
    throw "Modelfile not found: $ModelfilePath"
}

$modelfile = Get-Content -Encoding UTF8 -LiteralPath $ModelfilePath
$foundNumCtx = $false
$updatedModelfile = foreach ($line in $modelfile) {
    if ($line -match "^\s*PARAMETER\s+num_ctx\s+") {
        $foundNumCtx = $true
        "PARAMETER num_ctx $NumCtx"
    }
    else {
        $line
    }
}

if (-not $foundNumCtx) {
    $insertIndex = 0
    for ($i = 0; $i -lt $updatedModelfile.Count; $i++) {
        if ($updatedModelfile[$i] -match "^\s*PARAMETER\s+") {
            $insertIndex = $i + 1
        }
    }

    $before = if ($insertIndex -gt 0) { @($updatedModelfile[0..($insertIndex - 1)]) } else { @() }
    $after = if ($insertIndex -lt $updatedModelfile.Count) { @($updatedModelfile[$insertIndex..($updatedModelfile.Count - 1)]) } else { @() }
    $updatedModelfile = $before + "PARAMETER num_ctx $NumCtx" + $after
}

$updatedModelfile | Set-Content -LiteralPath $ModelfilePath -Encoding UTF8

Write-Host "Updated OLLAMA_CONTEXT_LENGTH=$NumCtx in $EnvPath"
Write-Host "Updated PARAMETER num_ctx $NumCtx in $ModelfilePath"
