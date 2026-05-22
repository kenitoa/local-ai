Set-StrictMode -Version Latest

function Get-OllamaRepoRoot {
    $current = $PSScriptRoot
    while ($current) {
        if ((Test-Path -LiteralPath (Join-Path $current ".git")) -or
            (Test-Path -LiteralPath (Join-Path $current ".env")) -or
            (Test-Path -LiteralPath (Join-Path $current "Cloud AI interface\CloudAI.Interface.csproj"))) {
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

function Read-OllamaDotEnv {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $map
    }

    Get-Content -Encoding UTF8 -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -lt 1) {
            return
        }

        $name = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim().Trim('"').Trim("'")
        if ($name) {
            $map[$name] = $value
        }
    }

    return $map
}

function Resolve-OllamaRepoPath {
    param(
        [string]$PathValue,
        [string]$RepoRoot
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $PathValue))
}

function Resolve-OllamaCli {
    param(
        [hashtable]$EnvValues,
        [string]$RepoRoot,
        [switch]$AllowPathFallback
    )

    if ($EnvValues.ContainsKey("OLLAMA_CLI")) {
        $configuredCli = Resolve-OllamaRepoPath -PathValue $EnvValues["OLLAMA_CLI"] -RepoRoot $RepoRoot
        if ($configuredCli -and (Test-Path -LiteralPath $configuredCli -PathType Leaf)) {
            return $configuredCli
        }
    }

    $defaultCli = Join-Path $PSScriptRoot "cli\ollama.exe"
    if (Test-Path -LiteralPath $defaultCli -PathType Leaf) {
        return $defaultCli
    }

    if ($AllowPathFallback) {
        $pathCommand = Get-Command ollama -ErrorAction SilentlyContinue
        if ($pathCommand) {
            return $pathCommand.Source
        }
    }

    return $null
}

function Initialize-OllamaLocalEnvironment {
    param([switch]$AllowPathFallback)

    $repoRoot = Get-OllamaRepoRoot
    $envPath = Join-Path $repoRoot ".env"
    $envValues = Read-OllamaDotEnv -Path $envPath

    foreach ($entry in $envValues.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }

    if ($envValues.ContainsKey("OLLAMA_MODELS")) {
        $modelsPath = Resolve-OllamaRepoPath -PathValue $envValues["OLLAMA_MODELS"] -RepoRoot $repoRoot
        New-Item -ItemType Directory -Path $modelsPath -Force | Out-Null
        [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelsPath, "Process")
    }

    $homePath = $null
    if ($envValues.ContainsKey("OLLAMA_HOME")) {
        $homePath = Resolve-OllamaRepoPath -PathValue $envValues["OLLAMA_HOME"] -RepoRoot $repoRoot
        New-Item -ItemType Directory -Path $homePath -Force | Out-Null
        [Environment]::SetEnvironmentVariable("OLLAMA_HOME", $homePath, "Process")
        [Environment]::SetEnvironmentVariable("HOME", $homePath, "Process")
        [Environment]::SetEnvironmentVariable("USERPROFILE", $homePath, "Process")
    }

    $hostBinding = if ($envValues.ContainsKey("OLLAMA_HOST")) { $envValues["OLLAMA_HOST"] } else { "127.0.0.1:11434" }
    $port = ($hostBinding -split ":")[-1]
    $endpoint = "http://localhost:$port"
    $ollamaCli = Resolve-OllamaCli -EnvValues $envValues -RepoRoot $repoRoot -AllowPathFallback:$AllowPathFallback

    return [pscustomobject][ordered]@{
        RepoRoot = $repoRoot
        EnvPath = $envPath
        EnvValues = $envValues
        OllamaCli = $ollamaCli
        HostBinding = $hostBinding
        Port = $port
        Endpoint = $endpoint
        TagsUrl = "$endpoint/api/tags"
        ModelsPath = $env:OLLAMA_MODELS
        HomePath = $homePath
    }
}
