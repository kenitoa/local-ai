<#
.SYNOPSIS
    local-ai MySQL 로컬 백업 스크립트.

.DESCRIPTION
    1) docker exec local-ai-mysql mysqldump 으로 DB 전체를 덤프.
    2) data/db_backups/ 에 gzip 압축으로 저장 (DB_BACKUP_DIR 로 변경 가능).
    3) DB_BACKUP_RETENTION_DAYS 가 지난 백업은 자동 삭제.
    4) 백업 파일 sha256 체크섬을 같이 기록.

.EXAMPLE
    .\scripts\db_backup.ps1
    .\scripts\db_backup.ps1 -Restore .\data\db_backups\local-ai_2026-04-30_120000.sql.gz
#>
[CmdletBinding(DefaultParameterSetName = 'Backup')]
param(
    [Parameter(ParameterSetName = 'Restore', Mandatory = $true)]
    [string]$Restore
)

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
        $hash = $v.IndexOf('#')
        if ($hash -ge 0) { $v = $v.Substring(0, $hash).Trim() }
        $map[$k] = $v
    }
    return $map
}

$env_map = Read-EnvFile -Path (Join-Path $ProjectRoot '.env')

$Container       = 'local-ai-mysql'
$RootPw          = $env_map['MYSQL_ROOT_PASSWORD']
$DbName          = $env_map['MYSQL_DATABASE']    ; if (-not $DbName) { $DbName = 'localai_db' }
$BackupDir       = $env_map['DB_BACKUP_DIR']     ; if (-not $BackupDir) { $BackupDir = './data/db_backups' }
$RetentionDays   = [int]($env_map['DB_BACKUP_RETENTION_DAYS'] | ForEach-Object { if ($_) { $_ } else { '14' } })

if (-not $RootPw) { throw 'MYSQL_ROOT_PASSWORD 가 .env 에 없습니다.' }

if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }
$BackupDir = (Resolve-Path -LiteralPath $BackupDir).Path

# 컨테이너 실행 중인지 확인
$state = (docker inspect --format '{{.State.Status}}' $Container 2>$null)
if ($LASTEXITCODE -ne 0) { throw "컨테이너 $Container 를 찾을 수 없습니다. docker compose up -d 먼저 실행하세요." }
if ($state.Trim() -ne 'running') { throw "컨테이너 상태가 'running' 이 아닙니다 (현재: $state)." }

# ============================================================
# RESTORE 모드
# ============================================================
if ($PSCmdlet.ParameterSetName -eq 'Restore') {
    if (-not (Test-Path $Restore)) { throw "백업 파일을 찾을 수 없습니다: $Restore" }

    Write-Host "==== restore ====" -ForegroundColor Yellow
    Write-Host "source : $Restore"
    Write-Host "target : $Container / $DbName"
    Write-Host ""
    $ans = Read-Host "기존 DB 의 데이터가 덮어쓰여집니다. 계속할까요? [y/N]"
    if ($ans -notmatch '^(y|yes)$') { Write-Host '취소되었습니다.'; return }

    $isGz = $Restore.ToLower().EndsWith('.gz')
    if ($isGz) {
        # gzip 해제 → 컨테이너 stdin 으로 mysql 주입
        $cmd = "gzip -dc `"$Restore`" | docker exec -i $Container mysql -uroot -p$RootPw $DbName"
    } else {
        $cmd = "docker exec -i $Container mysql -uroot -p$RootPw $DbName < `"$Restore`""
    }
    Write-Host "[exec] $cmd"
    cmd /c $cmd
    if ($LASTEXITCODE -ne 0) { throw "restore failed (exit $LASTEXITCODE)" }
    Write-Host '[OK] restore complete' -ForegroundColor Green
    return
}

# ============================================================
# BACKUP 모드
# ============================================================
$ts       = (Get-Date).ToString('yyyy-MM-dd_HHmmss')
$baseName = "localai_$ts.sql"
$sqlPath  = Join-Path $BackupDir $baseName
$gzPath   = $sqlPath + '.gz'

Write-Host "==== mysql backup ====" -ForegroundColor Cyan
Write-Host "container : $Container"
Write-Host "database  : $DbName"
Write-Host "output    : $gzPath"
Write-Host ""

# mysqldump → 호스트 파일로
# (Windows PowerShell 에서 stdout 을 그대로 파일로 받으면 인코딩 문제가 생기므로
#  컨테이너 안에서 덤프 후 docker cp 로 가져온다.)
$tmpInside = "/tmp/$baseName"
docker exec $Container sh -c "mysqldump --single-transaction --quick --default-character-set=utf8mb4 -uroot -p$RootPw $DbName > $tmpInside"
if ($LASTEXITCODE -ne 0) { throw "mysqldump failed (exit $LASTEXITCODE)" }

docker cp "${Container}:$tmpInside" $sqlPath
if ($LASTEXITCODE -ne 0) { throw "docker cp failed (exit $LASTEXITCODE)" }
docker exec $Container sh -c "rm -f $tmpInside" | Out-Null

# gzip 압축
$inStream  = [System.IO.File]::OpenRead($sqlPath)
$outStream = [System.IO.File]::Create($gzPath)
$gz        = New-Object System.IO.Compression.GZipStream($outStream, [System.IO.Compression.CompressionLevel]::Optimal)
try { $inStream.CopyTo($gz) } finally { $gz.Dispose(); $outStream.Dispose(); $inStream.Dispose() }
Remove-Item -LiteralPath $sqlPath -Force

# sha256
$hash = (Get-FileHash -LiteralPath $gzPath -Algorithm SHA256).Hash
"$hash  $(Split-Path $gzPath -Leaf)" | Out-File -LiteralPath ($gzPath + '.sha256') -Encoding ascii

$size = (Get-Item -LiteralPath $gzPath).Length
Write-Host ("[OK] backup written ({0:N1} MB)" -f ($size / 1MB)) -ForegroundColor Green
Write-Host "    sha256: $hash"

# 보존 정리
if ($RetentionDays -gt 0) {
    Write-Host ""
    Write-Host "[cleanup] 오래된 백업 삭제 (>= $RetentionDays 일)" -ForegroundColor Yellow
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem -LiteralPath $BackupDir -File -Filter 'localai_*.sql.gz*' -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.LastWriteTime -lt $cutoff) {
            Write-Host "  - $($_.Name)"
            Remove-Item -LiteralPath $_.FullName -Force
        }
    }
}

Write-Host ""
Write-Host "==== done ====" -ForegroundColor Cyan
