param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,
    [int]$Port = 11434
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Testing Ollama network access"
Write-Host "Target: $ServerIp`:$Port"
Write-Host ""

$result = Test-NetConnection $ServerIp -Port $Port

if ($result.TcpTestSucceeded) {
    Write-Host "Port is reachable." -ForegroundColor Green
}
else {
    Write-Host "Port is not reachable." -ForegroundColor Red
    Write-Host "Check OLLAMA_HOST, Windows firewall, server IP, and LAN/VPN routing."
}

$result
