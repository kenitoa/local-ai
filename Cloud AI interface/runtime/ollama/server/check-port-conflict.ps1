param(
    [int]$Port = 11434
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Checking port conflict"
Write-Host "Port: $Port"
Write-Host ""

$connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
if ($connections.Count -eq 0) {
    Write-Host "No process is listening on port $Port." -ForegroundColor Green
    exit 0
}

$results = @()
foreach ($connection in $connections) {
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    $results += [ordered]@{
        LocalAddress = $connection.LocalAddress
        LocalPort = $connection.LocalPort
        State = $connection.State
        PID = $connection.OwningProcess
        ProcessName = if ($process) { $process.ProcessName } else { "unknown" }
        Path = if ($process) { $process.Path } else { $null }
    }
}

$results | Format-Table -AutoSize

Write-Host ""
Write-Host "netstat equivalent:"
cmd /c "netstat -ano | findstr :$Port"

Write-Host ""
Write-Host "Process detail command:"
foreach ($item in $results) {
    Write-Host "tasklist /FI `"PID eq $($item.PID)`""
}

Write-Host ""
Write-Host "If port $Port is already in use, an existing Ollama server or another process is running." -ForegroundColor Yellow
