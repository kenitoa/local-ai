# =====================================================
# local-ai 런처 빌드 스크립트 (Windows .exe)
# =====================================================
#  사용법:
#     pwsh -File .\build.ps1
#  결과물:
#     .\dist\local-ai-launcher.exe
#  요구사항:
#     Go 1.21 이상  (https://go.dev/dl/)
# =====================================================

$ErrorActionPreference = 'Stop'

Push-Location $PSScriptRoot
try {
    if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
        Write-Error "Go 가 설치되어 있지 않습니다. https://go.dev/dl/ 에서 설치 후 다시 시도하세요."
    }

    $dist = Join-Path $PSScriptRoot 'dist'
    if (-not (Test-Path $dist)) {
        New-Item -ItemType Directory -Path $dist | Out-Null
    }

    $exe   = Join-Path $dist 'local-ai-launcher.exe'
    $setup = Join-Path $dist 'LocalAI_Setup.exe'

    Write-Host "[build] go build -> $exe"
    $env:GOOS   = 'windows'
    $env:GOARCH = 'amd64'
    $env:CGO_ENABLED = '0'

    # -s -w : 디버그 심볼 제거로 .exe 크기 축소
    go build -ldflags "-s -w" -o $exe .

    # Step 20: 동일 바이너리를 LocalAI_Setup.exe 라는 이름으로 복사한다.
    # 런처는 실행 파일 이름이 "LocalAI_Setup" 으로 시작하면 메뉴 없이
    # 자동 설치 흐름 (필수 구성 확인 → Compose → 브라우저) 으로 동작한다.
    Copy-Item -Path $exe -Destination $setup -Force
    Write-Host "[done ] $exe"
    Write-Host "[done ] $setup"
}
finally {
    Pop-Location
}
