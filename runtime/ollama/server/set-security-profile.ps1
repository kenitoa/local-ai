param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("localhost", "lan", "vpn", "reverse-proxy")]
    [string]$Profile,
    [string]$AllowedRemoteAddresses,
    [string]$EnvPath
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

    $updated | Set-Content -Encoding UTF8 -LiteralPath $Path
}

if (-not $EnvPath) {
    $EnvPath = Join-Path (Get-RepoRoot) ".env"
}

$hostValue = "127.0.0.1:11434"
$remoteValue = "None"
$notes = @()

switch ($Profile) {
    "localhost" {
        $hostValue = "127.0.0.1:11434"
        $remoteValue = "None"
        $notes += "개인 PC 단독 사용 구성입니다. Windows 방화벽 인바운드 허용이 필요하지 않습니다."
    }
    "lan" {
        $hostValue = "0.0.0.0:11434"
        $remoteValue = if ($AllowedRemoteAddresses) { $AllowedRemoteAddresses } else { "LocalSubnet" }
        $notes += "LAN 구성입니다. Windows 방화벽을 내부 대역으로 제한하세요."
    }
    "vpn" {
        $hostValue = "0.0.0.0:11434"
        $remoteValue = if ($AllowedRemoteAddresses) { $AllowedRemoteAddresses } else { "VPN_ONLY_SET_ME" }
        $notes += "VPN 구성입니다. Tailscale/WireGuard/VPN 내부 IP 대역만 허용하세요."
    }
    "reverse-proxy" {
        $hostValue = "127.0.0.1:11434"
        $remoteValue = "None"
        $notes += "공개 서버 구성입니다. Ollama는 localhost에만 두고 reverse proxy에서 인증과 HTTPS를 처리하세요."
    }
}

Set-DotEnvValue -Path $EnvPath -Name "OLLAMA_SECURITY_PROFILE" -Value $Profile
Set-DotEnvValue -Path $EnvPath -Name "OLLAMA_HOST" -Value $hostValue
Set-DotEnvValue -Path $EnvPath -Name "OLLAMA_ALLOWED_REMOTE_ADDRESSES" -Value $remoteValue

Write-Host "Security profile updated: $Profile" -ForegroundColor Green
Write-Host "OLLAMA_HOST=$hostValue"
Write-Host "OLLAMA_ALLOWED_REMOTE_ADDRESSES=$remoteValue"
$notes | ForEach-Object { Write-Host $_ }

if ($Profile -in @("lan", "vpn")) {
    Write-Host ""
    Write-Host "Apply firewall rule from Administrator PowerShell:"
    Write-Host ".\enable-firewall-rule.ps1 -RemoteAddress $remoteValue"
}
