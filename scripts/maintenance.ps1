<#
.SYNOPSIS
    local-ai 유지보수 스크립트.

.DESCRIPTION
    1) data/ 하위 사용자 데이터 중 mtime 이 DATA_RETENTION_DAYS 일 이상 지난
       파일을 data/archive/<YYYY-MM>/ 로 이동(보관 처리).
    2) data/archive/ 안의 파일도 ARCHIVE_RETENTION_DAYS 가 지나면 영구 삭제.
    3) logs/ 하위 .log 파일 중 mtime 이 LOG_RETENTION_DAYS 일 이상 지난 것은
       영구 삭제. (백엔드의 단일 .log 파일은 truncate 후 재시작 권장)

.PARAMETER WhatIf
    실제 이동/삭제 없이 작업 내용만 표시.

.EXAMPLE
    .\scripts\maintenance.ps1
    .\scripts\maintenance.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $ProjectRoot

# ---- .env 로드 ----
function Read-EnvFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -lt 0) { return }
        $k = $line.Substring(0, $eq).Trim()
        $v = $line.Substring($eq + 1).Trim()
        # 줄 끝 주석 제거
        $hash = $v.IndexOf('#')
        if ($hash -ge 0) { $v = $v.Substring(0, $hash).Trim() }
        $map[$k] = $v
    }
    return $map
}

$env_map = Read-EnvFile -Path (Join-Path $ProjectRoot '.env')

$DataDir              = $env_map['DATA_DIR']               ; if (-not $DataDir) { $DataDir = './data' }
$LogsDir              = $env_map['LOGS_DIR']               ; if (-not $LogsDir) { $LogsDir = './logs' }
$DataRetentionDays    = [int]($env_map['DATA_RETENTION_DAYS']    | ForEach-Object { if ($_) { $_ } else { '30' } })
$ArchiveRetentionDays = [int]($env_map['ARCHIVE_RETENTION_DAYS'] | ForEach-Object { if ($_) { $_ } else { '0' } })
$LogRetentionDays     = [int]($env_map['LOG_RETENTION_DAYS']     | ForEach-Object { if ($_) { $_ } else { '7' } })

$DataDir = (Resolve-Path -LiteralPath $DataDir -ErrorAction SilentlyContinue) ; if (-not $DataDir) { $DataDir = Join-Path $ProjectRoot 'data' }
$LogsDir = (Resolve-Path -LiteralPath $LogsDir -ErrorAction SilentlyContinue) ; if (-not $LogsDir) { $LogsDir = Join-Path $ProjectRoot 'logs' }

$ArchiveRoot = Join-Path $DataDir 'archive'
$now = Get-Date

Write-Host "==== local-ai maintenance ====" -ForegroundColor Cyan
Write-Host "DataDir              : $DataDir"
Write-Host "LogsDir              : $LogsDir"
Write-Host "DataRetentionDays    : $DataRetentionDays"
Write-Host "ArchiveRetentionDays : $ArchiveRetentionDays"
Write-Host "LogRetentionDays     : $LogRetentionDays"
Write-Host ""

# ---- 1) 사용자 데이터 archive 이동 ----
# archive 대상: 사용자 산출물 카테고리 (모델 가중치/시스템 폴더는 제외)
$UserDataCategories = @(
    'image_data',
    'code_data',
    'model_answers',
    'embeddings'
)

if ($DataRetentionDays -gt 0) {
    Write-Host "[1] 사용자 데이터 archive 처리 (>= $DataRetentionDays 일)" -ForegroundColor Yellow
    $cutoff = $now.AddDays(-$DataRetentionDays)
    $movedCount = 0; $movedBytes = 0L

    foreach ($cat in $UserDataCategories) {
        $catRoot = Join-Path $DataDir $cat
        if (-not (Test-Path $catRoot)) { continue }
        Get-ChildItem -LiteralPath $catRoot -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.LastWriteTime -ge $cutoff) { return }
            $rel = $_.FullName.Substring($DataDir.Path.Length).TrimStart('\','/')
            $bucket = $_.LastWriteTime.ToString('yyyy-MM')
            $dest = Join-Path (Join-Path $ArchiveRoot $bucket) $rel
            $destDir = Split-Path $dest -Parent
            if ($PSCmdlet.ShouldProcess($_.FullName, "Move to $dest")) {
                if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
                Move-Item -LiteralPath $_.FullName -Destination $dest -Force
            }
            $movedCount++; $movedBytes += $_.Length
        }
    }
    "{0,-30} {1,5} files, {2,8:N1} MB moved" -f 'archive total:', $movedCount, ($movedBytes / 1MB) | Write-Host
} else {
    Write-Host "[1] DATA_RETENTION_DAYS=0 → skip" -ForegroundColor DarkGray
}

# ---- 2) archive 영구 삭제 ----
if ($ArchiveRetentionDays -gt 0 -and (Test-Path $ArchiveRoot)) {
    Write-Host ""
    Write-Host "[2] archive 영구 삭제 (>= $ArchiveRetentionDays 일)" -ForegroundColor Yellow
    $cutoff = $now.AddDays(-$ArchiveRetentionDays)
    $delCount = 0; $delBytes = 0L
    Get-ChildItem -LiteralPath $ArchiveRoot -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.LastWriteTime -ge $cutoff) { return }
        if ($PSCmdlet.ShouldProcess($_.FullName, "Delete")) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
        $delCount++; $delBytes += $_.Length
    }
    "{0,-30} {1,5} files, {2,8:N1} MB deleted" -f 'archive purge:', $delCount, ($delBytes / 1MB) | Write-Host

    # 빈 디렉터리 정리
    Get-ChildItem -LiteralPath $ArchiveRoot -Recurse -Directory -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Where-Object { @(Get-ChildItem -LiteralPath $_.FullName -Force).Count -eq 0 } |
        ForEach-Object {
            if ($PSCmdlet.ShouldProcess($_.FullName, "Remove empty dir")) {
                Remove-Item -LiteralPath $_.FullName -Force
            }
        }
} else {
    Write-Host ""
    Write-Host "[2] ARCHIVE_RETENTION_DAYS=0 → 영구 보관 모드 (삭제 안 함)" -ForegroundColor DarkGray
}

# ---- 3) 로그 삭제 ----
if ($LogRetentionDays -gt 0 -and (Test-Path $LogsDir)) {
    Write-Host ""
    Write-Host "[3] 로그 파일 삭제 (>= $LogRetentionDays 일)" -ForegroundColor Yellow
    $cutoff = $now.AddDays(-$LogRetentionDays)
    $delCount = 0; $delBytes = 0L
    Get-ChildItem -LiteralPath $LogsDir -Recurse -File -Include *.log,*.log.*,*.gz -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.LastWriteTime -ge $cutoff) { return }
        if ($PSCmdlet.ShouldProcess($_.FullName, "Delete")) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
        $delCount++; $delBytes += $_.Length
    }
    "{0,-30} {1,5} files, {2,8:N1} MB deleted" -f 'logs purge:', $delCount, ($delBytes / 1MB) | Write-Host
} else {
    Write-Host ""
    Write-Host "[3] LOG_RETENTION_DAYS=0 → skip" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "==== done ====" -ForegroundColor Cyan
