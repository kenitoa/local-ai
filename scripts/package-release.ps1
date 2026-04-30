# =====================================================
# local-ai 최종 배포 패키지 빌드 스크립트 (Step 20)
# =====================================================
#  사진 20단계 흐름:
#    사용자 다운로드
#       ↓
#    LocalAI_Setup.exe 실행
#       ↓
#    필수 구성 확인 → Docker Compose 실행 → 브라우저 자동 실행 → 로컬 AI 사용
#
#  본 스크립트는 위 흐름을 만족하는 배포 산출물을 생성한다.
#
#  사용법:
#     pwsh -File .\scripts\package-release.ps1
#     pwsh -File .\scripts\package-release.ps1 -SkipBuild   # launcher 재빌드 생략
#     pwsh -File .\scripts\package-release.ps1 -NoZip       # zip 생략(폴더만)
#
#  결과물:
#     dist/LocalAI_Setup/             ← 사용자에게 그대로 전달 가능한 폴더
#     dist/LocalAI_Setup-<ver>.zip    ← 배포용 압축 파일
# =====================================================

[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$NoZip,
    [string]$Version = (Get-Date -Format 'yyyyMMdd')
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host "[pkg ] repo root : $repoRoot"
    Write-Host "[pkg ] version   : $Version"

    # ---------------------------------------------------------------
    # 1) launcher 빌드 → LocalAI_Setup.exe / local-ai-launcher.exe
    # ---------------------------------------------------------------
    $launcherDir  = Join-Path $repoRoot 'launcher'
    $launcherDist = Join-Path $launcherDir 'dist'
    $setupExe     = Join-Path $launcherDist 'LocalAI_Setup.exe'
    $menuExe      = Join-Path $launcherDist 'local-ai-launcher.exe'

    if (-not $SkipBuild) {
        Write-Host "[pkg ] launcher 빌드 실행..."
        pwsh -File (Join-Path $launcherDir 'build.ps1')
    } else {
        Write-Host "[pkg ] -SkipBuild → launcher 재빌드 생략"
    }

    foreach ($f in @($setupExe, $menuExe)) {
        if (-not (Test-Path $f)) {
            throw "필수 산출물이 없습니다: $f  (먼저 launcher/build.ps1 을 실행하세요)"
        }
    }

    # ---------------------------------------------------------------
    # 2) 배포 폴더 구성
    # ---------------------------------------------------------------
    $distRoot = Join-Path $repoRoot 'dist'
    $pkgDir   = Join-Path $distRoot 'LocalAI_Setup'
    if (Test-Path $pkgDir) { Remove-Item $pkgDir -Recurse -Force }
    New-Item -ItemType Directory -Path $pkgDir | Out-Null

    Write-Host "[pkg ] 패키지 폴더 생성: $pkgDir"

    # 2-1) launcher 산출물
    Copy-Item $setupExe (Join-Path $pkgDir 'LocalAI_Setup.exe') -Force
    Copy-Item $menuExe  (Join-Path $pkgDir 'local-ai-launcher.exe') -Force

    # 2-2) Compose / 환경 / 문서
    Copy-Item (Join-Path $repoRoot 'docker-compose.yml') $pkgDir -Force
    Copy-Item (Join-Path $repoRoot '.env.example')        $pkgDir -Force
    Copy-Item (Join-Path $repoRoot 'README.md')           $pkgDir -Force
    if (Test-Path (Join-Path $repoRoot '.gitignore')) {
        Copy-Item (Join-Path $repoRoot '.gitignore') $pkgDir -Force
    }
    if (Test-Path (Join-Path $repoRoot '.gitattributes')) {
        Copy-Item (Join-Path $repoRoot '.gitattributes') $pkgDir -Force
    }

    # 2-3) 서비스 소스 (Docker Compose 가 build 컨텍스트로 사용)
    $services = @(
        'backend','web-ui','model-server','vision-server',
        'embedding-server','language-worker','hardware-detector',
        'mysql','docker','scripts'
    )
    foreach ($svc in $services) {
        $src = Join-Path $repoRoot $svc
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $pkgDir $svc) -Recurse -Force
        }
    }

    # 2-4) 첫 실행에서 자동 생성되지만, 미리 만들어 두면 권한 이슈가 줄어듬
    foreach ($d in @('data','models','logs')) {
        New-Item -ItemType Directory -Path (Join-Path $pkgDir $d) -Force | Out-Null
        New-Item -ItemType File `
            -Path (Join-Path $pkgDir (Join-Path $d '.gitkeep')) -Force | Out-Null
    }

    # 2-5) 사용자용 빠른 시작 안내
    $quickStart = @"
============================================================
 LocalAI Setup
============================================================

[설치 흐름]

  1. 본 폴더 안의 'LocalAI_Setup.exe' 를 더블클릭합니다.
  2. 자동으로 다음 작업이 실행됩니다.
       - 필수 구성(Docker Desktop) 확인
       - .env 자동 생성 / GPU·CPU 자동 감지
       - docker compose up -d --build
       - 서비스 health check
       - 기본 브라우저로 Web UI 자동 열기
  3. 브라우저가 열리면 바로 LocalAI 를 사용할 수 있습니다.

[사전 요구 사항]

  - Windows 10/11 (64-bit)
  - Docker Desktop 4.x 이상이 설치되고 실행 중이어야 합니다.
       https://www.docker.com/products/docker-desktop/
  - (선택) NVIDIA GPU 사용 시 NVIDIA 드라이버 + WSL2 GPU 지원

[다음 실행부터]

  - 일상 운영(실행/중지/로그/복구)은 'local-ai-launcher.exe' 를
    더블클릭해서 메뉴에서 선택하세요.
  - 'LocalAI_Setup.exe' 는 다시 실행해도 안전하게 동작합니다.

자세한 내용은 README.md 와 launcher/README.md 를 참고하세요.
"@
    Set-Content -Path (Join-Path $pkgDir 'QUICKSTART.txt') `
        -Value $quickStart -Encoding UTF8

    # ---------------------------------------------------------------
    # 3) ZIP 압축
    # ---------------------------------------------------------------
    if (-not $NoZip) {
        $zipPath = Join-Path $distRoot ("LocalAI_Setup-$Version.zip")
        if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
        Write-Host "[pkg ] 압축: $zipPath"
        Compress-Archive -Path (Join-Path $pkgDir '*') -DestinationPath $zipPath -Force
        Write-Host "[done] $zipPath"
    }

    Write-Host "[done] $pkgDir"
}
finally {
    Pop-Location
}
