param(
    [string]$TaskName = "Ollama Local Server"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existingTask) {
    Write-Host "Scheduled task does not exist: $TaskName" -ForegroundColor Yellow
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Scheduled task removed: $TaskName" -ForegroundColor Green
