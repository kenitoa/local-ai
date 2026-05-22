param(
    [string]$TaskName = "Ollama Local Server",
    [switch]$RunLevelHighest,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$StartScript = Join-Path $PSScriptRoot "start-server.ps1"
if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "start-server.ps1 not found: $StartScript"
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask -and -not $Force) {
    Write-Host "Scheduled task already exists: $TaskName" -ForegroundColor Yellow
    Write-Host "Use -Force to replace it."
    exit 0
}

if ($existingTask -and $Force) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$actionArgument = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgument
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$principal = if ($RunLevelHighest) {
    New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Highest
}
else {
    New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Start Ollama local server on user logon through local-ai start-server.ps1." | Out-Null

Write-Host "Scheduled task registered: $TaskName" -ForegroundColor Green
Write-Host "Trigger: user logon"
Write-Host "Action: powershell.exe $actionArgument"
Write-Host "RunLevel: $(if ($RunLevelHighest) { 'Highest' } else { 'Limited' })"
Write-Host ""
Write-Host "The startup script checks port 11434 first. If Ollama is not running, the task stays alive as the server process."
