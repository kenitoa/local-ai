<#
.SYNOPSIS
    local-ai 의 maintenance.ps1 / db_backup.ps1 을 Windows 작업 스케줄러에
    매일 자동 실행되도록 등록한다.

.DESCRIPTION
    - 작업 1: LocalAI-Maintenance   (매일 03:00) → 사용자 데이터 archive + 로그 정리
    - 작업 2: LocalAI-DBBackup       (매일 03:30) → MySQL 로컬 백업 (보존: DB_BACKUP_RETENTION_DAYS)

    관리자 권한 PowerShell 에서 실행하세요.
    제거: -Remove

.EXAMPLE
    # 등록 (관리자 PowerShell)
    .\scripts\install-windows-tasks.ps1

    # 제거
    .\scripts\install-windows-tasks.ps1 -Remove
#>
[CmdletBinding()]
param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$tasks = @(
    @{ Name = 'LocalAI-Maintenance'; Script = 'scripts\maintenance.ps1'; Time = '03:00' }
    @{ Name = 'LocalAI-DBBackup';    Script = 'scripts\db_backup.ps1';   Time = '03:30' }
)

# 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    throw '관리자 권한이 필요합니다. PowerShell 을 "관리자 권한으로 실행" 후 다시 시도하세요.'
}

if ($Remove) {
    foreach ($t in $tasks) {
        if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
            Write-Host "[OK] removed: $($t.Name)" -ForegroundColor Green
        } else {
            Write-Host "[skip] not found: $($t.Name)" -ForegroundColor DarkGray
        }
    }
    return
}

foreach ($t in $tasks) {
    $scriptPath = Join-Path $ProjectRoot $t.Script
    if (-not (Test-Path $scriptPath)) { throw "스크립트 없음: $scriptPath" }

    $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType S4U -RunLevel Highest

    if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
    }

    Register-ScheduledTask -TaskName $t.Name `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description "local-ai daily maintenance" | Out-Null

    Write-Host "[OK] registered: $($t.Name)  (daily $($t.Time))" -ForegroundColor Green
    Write-Host "      $scriptPath"
}

Write-Host ""
Write-Host "확인: taskschd.msc → 작업 스케줄러 라이브러리 → LocalAI-*" -ForegroundColor Cyan
