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

    $exe = Join-Path $dist 'local-ai-launcher.exe'

    Write-Host "[build] go build -> $exe"
    $env:GOOS   = 'windows'
    $env:GOARCH = 'amd64'
    $env:CGO_ENABLED = '0'

    # -s -w : 디버그 심볼 제거로 .exe 크기 축소
    go build -ldflags "-s -w" -o $exe .

    Write-Host "[done ] $exe"
}
finally {
    Pop-Location
}
