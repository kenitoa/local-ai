# local-ai launcher (Windows .exe)

3단계 산출물 — local-ai 스택을 한 번에 기동/관리하는 Windows 런처입니다.
**AI 자체가 아니라 설치/실행 관리자** 역할만 합니다.

## 실행 흐름

```
launcher.exe 실행
    ↓
Docker Desktop 설치 여부 확인
    ↓
Docker 실행 여부 확인
    ↓
Docker Compose 사용 가능 확인
    ↓
docker-compose.yml 확인
    ↓
로컬 폴더 생성 (data / models / logs)
    ↓
.env 자동 생성 (.env.example 복사)
    ↓
GPU / CPU 모드 감지 (.env 의 MODEL_SERVER_DEVICE 갱신)
    ↓
docker compose up -d
    ↓
서비스 health check (backend /health, web-ui)
    ↓
브라우저에서 Web UI 자동 실행
```

실패 시에는 `docker compose logs --tail=80` 결과를 콘솔에 출력하고 종료합니다.

## 빌드

요구사항: **Go 1.21+** ([설치](https://go.dev/dl/))

```powershell
cd launcher
pwsh -File .\build.ps1
```

산출물: `launcher/dist/local-ai-launcher.exe`

## 배포 / 실행

`local-ai-launcher.exe` 를 프로젝트 루트(또는 `launcher/dist/` 안)에 둔 채 실행합니다.
런처는 자동으로 상위 폴더에서 `docker-compose.yml` 을 찾습니다.

```powershell
.\dist\local-ai-launcher.exe
```

## 체크리스트 매핑

| 항목 | 구현 위치 (`main.go`) |
| --- | --- |
| Docker Desktop 설치 여부 확인 | `checkDockerInstalled` |
| Docker 실행 여부 확인 | `checkDockerRunning` |
| Docker Compose 사용 가능 여부 확인 | `checkCompose` (v2 → v1 폴백) |
| 로컬 폴더 생성 | `ensureDirs` (`data`/`models`/`logs`) |
| `.env` 자동 생성 | `ensureEnv` |
| GPU/CPU 모드 설정 | `detectDevice` (`nvidia-smi`/macOS arm64) |
| `docker compose up -d` 실행 | `composeUp` |
| 서비스 상태 확인 | `waitForHealth` |
| 실패 시 로그 표시 | `showLogs` |
| 성공 시 Web UI 자동 열기 | `openBrowser` |

## 비고

- `.env` 의 `MODEL_SERVER_DEVICE` 가 `auto` 인 경우에만 자동 감지 결과로 덮어씁니다.
  사용자가 명시적으로 `cpu` / `cuda` / `mps` 로 적어두었다면 그대로 둡니다.
- 포트는 `.env` 의 `WEB_UI_PORT`, `BACKEND_PORT` 값을 사용합니다 (기본 3000 / 8000).
- 초기 단계에서는 Go 단일 바이너리로 충분하지만, 추후 시스템 트레이/자동 업데이트 등이
  필요해지면 C# (WPF) 로 대체하는 것을 검토하세요.
