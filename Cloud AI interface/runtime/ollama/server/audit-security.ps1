param(
    [string]$EnvPath,
    [string]$FirewallRuleName = "Ollama Local Server 11434",
    [int]$Port = 11434
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Read-DotEnv {
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
        $map[$name] = $value
    }

    return $map
}

function Add-Finding {
    param(
        [System.Collections.Generic.List[object]]$Findings,
        [string]$Level,
        [string]$Message
    )

    $Findings.Add([ordered]@{
        level = $Level
        message = $Message
    })
}

if (-not $EnvPath) {
    $EnvPath = Join-Path (Get-RepoRoot) ".env"
}

$envValues = Read-DotEnv -Path $EnvPath
$profile = if ($envValues.ContainsKey("OLLAMA_SECURITY_PROFILE")) { $envValues["OLLAMA_SECURITY_PROFILE"] } else { "unknown" }
$hostValue = if ($envValues.ContainsKey("OLLAMA_HOST")) { $envValues["OLLAMA_HOST"] } else { "127.0.0.1:11434" }
$remoteValue = if ($envValues.ContainsKey("OLLAMA_ALLOWED_REMOTE_ADDRESSES")) { $envValues["OLLAMA_ALLOWED_REMOTE_ADDRESSES"] } else { "" }

$findings = [System.Collections.Generic.List[object]]::new()

if ($hostValue -match "^0\.0\.0\.0:") {
    Add-Finding $findings "info" "OLLAMA_HOST is bound to all interfaces: $hostValue"

    if ([string]::IsNullOrWhiteSpace($remoteValue) -or $remoteValue -eq "Any") {
        Add-Finding $findings "error" "0.0.0.0 requires OLLAMA_ALLOWED_REMOTE_ADDRESSES to be LocalSubnet, VPN CIDR, or explicit internal IP range. Never use Any for direct Ollama exposure."
    }
}
elseif ($hostValue -match "^(127\.0\.0\.1|localhost):") {
    Add-Finding $findings "ok" "Ollama is localhost-only: $hostValue"
}
else {
    Add-Finding $findings "warning" "OLLAMA_HOST uses a non-standard binding: $hostValue"
}

switch ($profile) {
    "localhost" {
        if ($hostValue -notmatch "^(127\.0\.0\.1|localhost):") {
            Add-Finding $findings "error" "localhost profile must use 127.0.0.1 or localhost."
        }
    }
    "lan" {
        if ($hostValue -notmatch "^0\.0\.0\.0:") {
            Add-Finding $findings "warning" "lan profile usually uses OLLAMA_HOST=0.0.0.0:11434."
        }
        if ($remoteValue -eq "Any") {
            Add-Finding $findings "error" "LAN profile must not allow RemoteAddress=Any."
        }
    }
    "vpn" {
        if ($remoteValue -in @("", "Any", "LocalSubnet", "VPN_ONLY_SET_ME")) {
            Add-Finding $findings "error" "VPN profile requires an explicit VPN-only CIDR or IP range."
        }
    }
    "reverse-proxy" {
        if ($hostValue -notmatch "^(127\.0\.0\.1|localhost):") {
            Add-Finding $findings "error" "reverse-proxy profile must keep Ollama bound to localhost."
        }
    }
    default {
        Add-Finding $findings "warning" "Unknown or missing OLLAMA_SECURITY_PROFILE: $profile"
    }
}

$firewallRule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
if ($firewallRule) {
    $portFilters = @($firewallRule | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue)
    $addressFilters = @($firewallRule | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue)
    $remoteAddresses = @($addressFilters | ForEach-Object { $_.RemoteAddress })

    if ($hostValue -match "^0\.0\.0\.0:") {
        if ($remoteAddresses -contains "Any") {
            Add-Finding $findings "error" "Firewall rule '$FirewallRuleName' allows RemoteAddress=Any."
        }
        else {
            Add-Finding $findings "ok" "Firewall rule exists and does not allow Any remote address: $($remoteAddresses -join ', ')"
        }
    }

    if (-not ($portFilters | Where-Object { $_.LocalPort -contains "$Port" -or $_.LocalPort -eq $Port })) {
        Add-Finding $findings "warning" "Firewall rule exists but does not clearly target port $Port."
    }
}
else {
    if ($hostValue -match "^0\.0\.0\.0:") {
        Add-Finding $findings "error" "OLLAMA_HOST opens LAN access but firewall rule '$FirewallRuleName' was not found."
    }
    else {
        Add-Finding $findings "ok" "No Ollama firewall rule found; localhost profile does not require one."
    }
}

$connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
if ($connections.Count -gt 0) {
    $owners = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    Add-Finding $findings "info" "Port $Port is currently in use by PID(s): $($owners -join ', ')"
}
else {
    Add-Finding $findings "info" "Port $Port is not currently listening."
}

Write-Host "Ollama security audit"
Write-Host "Env: $EnvPath"
Write-Host "Profile: $profile"
Write-Host "OLLAMA_HOST: $hostValue"
Write-Host "OLLAMA_ALLOWED_REMOTE_ADDRESSES: $remoteValue"
Write-Host ""

foreach ($finding in $findings) {
    $color = switch ($finding.level) {
        "ok" { "Green" }
        "info" { "Cyan" }
        "warning" { "Yellow" }
        "error" { "Red" }
        default { "White" }
    }

    Write-Host "[$($finding.level)] $($finding.message)" -ForegroundColor $color
}

$hasError = @($findings | Where-Object { $_.level -eq "error" }).Count -gt 0
if ($hasError) {
    exit 2
}

$hasWarning = @($findings | Where-Object { $_.level -eq "warning" }).Count -gt 0
if ($hasWarning) {
    exit 1
}

exit 0
