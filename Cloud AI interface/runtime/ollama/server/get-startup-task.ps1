param(
    [string]$TaskName = "Ollama Local Server"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Scheduled task not found: $TaskName" -ForegroundColor Yellow
    exit 1
}

$task | Format-List TaskName, State, Author, Description
$task.Actions | Format-List
$task.Triggers | Format-List
