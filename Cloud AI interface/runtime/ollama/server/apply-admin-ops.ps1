param(
    [string]$LogPath = (Join-Path $PSScriptRoot "admin-ops-report.log")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Write-AdminLog {
    param([string]$Message)
    $line = "[$((Get-Date).ToString("o"))] $Message"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $line
    Write-Host $Message
}

Remove-Item -LiteralPath $LogPath -Force -ErrorAction SilentlyContinue

Write-AdminLog "Starting administrator operations."
Write-AdminLog "WorkingDirectory=$PSScriptRoot"

try {
    & "$PSScriptRoot\enable-firewall-rule.ps1" 2>&1 |
        ForEach-Object { Write-AdminLog $_.ToString() }
    Write-AdminLog "Firewall step completed with exit code $LASTEXITCODE."
}
catch {
    Write-AdminLog "Firewall step failed: $($_.Exception.Message)"
}

try {
    & "$PSScriptRoot\register-startup-task.ps1" -RunLevelHighest -Force 2>&1 |
        ForEach-Object { Write-AdminLog $_.ToString() }
    Write-AdminLog "Startup task step completed with exit code $LASTEXITCODE."
}
catch {
    Write-AdminLog "Startup task step failed: $($_.Exception.Message)"
}

try {
    & "$PSScriptRoot\audit-security.ps1" 2>&1 |
        ForEach-Object { Write-AdminLog $_.ToString() }
    Write-AdminLog "Security audit step completed with exit code $LASTEXITCODE."
}
catch {
    Write-AdminLog "Security audit step failed: $($_.Exception.Message)"
}

Write-AdminLog "Administrator operations finished."
