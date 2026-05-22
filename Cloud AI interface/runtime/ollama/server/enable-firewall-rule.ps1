param(
    [string]$DisplayName = "Ollama Local Server 11434",
    [int]$LocalPort = 11434,
    [string]$RemoteAddress,
    [switch]$AllowAnyRemoteAddress
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RepoRoot {
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

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
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
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$RepoRoot = Get-RepoRoot
Import-DotEnv -Path (Join-Path $RepoRoot ".env")

if (-not (Test-Administrator)) {
    throw "Run this script from an Administrator PowerShell session."
}

if ($AllowAnyRemoteAddress) {
    $RemoteAddress = "Any"
}
elseif ([string]::IsNullOrWhiteSpace($RemoteAddress)) {
    $RemoteAddress = if ($env:OLLAMA_ALLOWED_REMOTE_ADDRESSES) {
        $env:OLLAMA_ALLOWED_REMOTE_ADDRESSES
    }
    else {
        "LocalSubnet"
    }
}

if ($RemoteAddress -eq "Any" -and -not $AllowAnyRemoteAddress) {
    throw "RemoteAddress=Any is not allowed by default. Use -AllowAnyRemoteAddress only for a reverse-proxy/VPN-protected design."
}

$existingRule = Get-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "Firewall rule already exists: $DisplayName" -ForegroundColor Yellow
    $existingRule | Format-Table DisplayName, Enabled, Direction, Action -AutoSize
    exit 0
}

New-NetFirewallRule `
    -DisplayName $DisplayName `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $LocalPort `
    -RemoteAddress $RemoteAddress `
    -Action Allow | Out-Null

Write-Host "Firewall rule created: $DisplayName" -ForegroundColor Green
Write-Host "LocalPort=$LocalPort"
Write-Host "RemoteAddress=$RemoteAddress"
