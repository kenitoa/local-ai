param(
    [switch]$Detach,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

function Find-Python {
    $pythonCandidates = @(
        ".\.venv\Scripts\python.exe",
        "..\.venv\Scripts\python.exe",
        "..\..\.venv\Scripts\python.exe",
        "python",
        "py"
    )

    foreach ($candidate in $pythonCandidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $candidate
        }
    }

    throw "Python was not found. Install Python or create a local .venv first."
}

function Read-RuntimeEnv {
    if (-not (Test-Path ".runtime.env")) {
        throw ".runtime.env was not created by scripts/preflight.py."
    }

    $runtime = @{}
    Get-Content ".runtime.env" | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line.Split("=", 2)
        if ($parts.Length -eq 2) {
            $runtime[$parts[0]] = $parts[1]
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
    return $runtime
}

function New-ComposeArgs($composeFiles) {
    if (-not $composeFiles) {
        throw "COMPOSE_FILES was not written to .runtime.env."
    }

    $composeArgs = @()
    foreach ($file in $composeFiles.Split(":")) {
        if (-not (Test-Path $file)) {
            throw "Compose file not found: $file"
        }
        $composeArgs += @("-f", $file)
    }
    return $composeArgs
}

$python = Find-Python
if ($python -eq "py") {
    & $python -3 scripts/preflight.py
} else {
    & $python scripts/preflight.py
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$runtime = Read-RuntimeEnv
$composeArgs = New-ComposeArgs $runtime["COMPOSE_FILES"]
$upArgs = @("up")
if (-not $NoBuild) {
    $upArgs += "--build"
}
if ($Detach) {
    $upArgs += "--detach"
}

Write-Host "Selected AI device: $($runtime["AI_DEVICE"])"
Write-Host "Selected LLM backend: $($runtime["LLM_BACKEND"])"
Write-Host "Compose files: $($runtime["COMPOSE_FILES"])"
Write-Host "Command: docker compose $($composeArgs -join ' ') $($upArgs -join ' ')"

docker compose @composeArgs @upArgs
