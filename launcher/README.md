# local-ai launcher (Step 18 — `.exe` 패키징)

최종 사용자가 **`launcher.exe` 하나만 실행**하면 local-ai 스택을
설치 / 실행 / 점검 / 복구할 수 있는 메뉴형 Windows 런처입니다.

## 패키지 구조

배포 시에는 다음과 같이 압축 / 폴더로 묶어 전달합니다.

```
LocalAI_Setup/
├── launcher.exe           ← 본 런처 (launcher/dist/local-ai-launcher.exe)
├── docker-compose.yml
├── .env.example
├── scripts/
├── models/                ← (비어 있음, 첫 실행 시 모델 다운로드 위치)
├── data/
├── mysql/                 ← init SQL
├── logs/
└── README.md
```

`launcher.exe` 는 자기 자신이 위치한 폴더(또는 그 상위)에서
`docker-compose.yml` 을 자동으로 찾습니다.

## 실행 메뉴

```
====================================================
 local-ai launcher
====================================================
 [1]  최초 설치
 [2]  실행
 [3]  중지
 [4]  재시작
 [5]  로그 보기
 [6]  모델 상태 확인
 [7]  DB 상태 확인
 [8]  GPU/CPU 상태 확인
 [9]  Web UI 열기
 [10] Docker 서비스 복구
 [0]  종료
```

| 메뉴 | 기능 | 내부 동작 |
| --- | --- | --- |
| 1 | 최초 설치 | Docker / Compose 점검 → `data` `models` `logs` 생성 → `.env` 자동 생성 → GPU/CPU 자동 감지 후 `MODEL_SERVER_DEVICE` 갱신 → `docker compose up -d --build` → health check → 브라우저로 Web UI 오픈 |
| 2 | 실행 | `docker compose up -d` |
| 3 | 중지 | `docker compose stop` |
| 4 | 재시작 | `docker compose restart` |
| 5 | 로그 보기 | 서비스명 입력(빈 값=전체), follow 모드 선택 → `docker compose logs --tail=200 [-f] [svc]` |
| 6 | 모델 상태 확인 | `docker compose ps` + 각 서버 `/health` 호출 + `.env` 의 기본 모델 표시 |
| 7 | DB 상태 확인 | `local-ai-mysql` 컨테이너 상태 + `mysqladmin ping` + `SELECT NOW(), DATABASE(), VERSION()` |
| 8 | GPU/CPU 상태 확인 | OS/Arch/CPU 코어, `MODEL_SERVER_DEVICE`, `nvidia-smi`, hardware-detector `/health` |
| 9 | Web UI 열기 | `.env` 의 `WEB_UI_PORT` 로 도달 가능 여부 확인 후 기본 브라우저로 오픈 |
| 10 | Docker 서비스 복구 | 확인 후 `docker compose down` → `docker compose up -d --build` → health check |

실패 시에는 자동으로 `docker compose logs --tail=80` 을 출력하여 원인을
바로 확인할 수 있게 했습니다.

## 빌드

요구사항: **Go 1.21+** ([설치](https://go.dev/dl/))

```powershell
cd launcher
pwsh -File .\build.ps1
```

산출물: `launcher/dist/local-ai-launcher.exe`

## 배포 / 실행

`local-ai-launcher.exe` 를 프로젝트 루트(또는 `launcher/dist/`) 에 두고 실행합니다.
런처는 자동으로 상위 폴더에서 `docker-compose.yml` 을 찾습니다.

```powershell
.\dist\local-ai-launcher.exe
```

## 비고

- `.env` 의 `MODEL_SERVER_DEVICE` 가 `auto` 일 때만 [1] 최초 설치에서
  자동 감지 결과(`cpu` / `cuda` / `mps`)로 덮어씁니다. 사용자가 명시
  적으로 값을 적어두었다면 그대로 유지합니다.
- 포트는 `.env` 의 `WEB_UI_PORT`, `BACKEND_PORT`, `MYSQL_PORT`,
  `MODEL_SERVER_PORT`, `VISION_SERVER_PORT`, `EMBEDDING_SERVER_PORT`,
  `LANGUAGE_WORKER_PORT`, `HARDWARE_DETECTOR_PORT` 값을 읽어 사용합니다.
- Compose v2 (`docker compose`) 를 우선 사용하고, 없으면 v1
  (`docker-compose`) 으로 자동 폴백합니다.
- 초기 단계에서는 Go 단일 바이너리로 충분하지만, 향후 트레이 아이콘
  이나 자동 업데이트 등이 필요해지면 C# (WPF) 등으로 재작성하는 것을
  검토하세요.

## Step 20 — 최종 배포 구조 (`LocalAI_Setup.exe`)

사진 20단계 흐름을 그대로 구현한 산출물입니다.

```
사용자 다운로드
   ↓
LocalAI_Setup.exe 실행
   ↓
필수 구성 확인  (Docker Desktop / Compose)
   ↓
Docker Compose 실행  (up -d --build, health check)
   ↓
브라우저 자동 실행  (http://localhost:WEB_UI_PORT)
   ↓
로컬 AI 사용
```

### 동작 원리

`launcher` 와 `LocalAI_Setup.exe` 는 **동일 바이너리**이며,
실행 파일 이름이 `LocalAI_Setup` 으로 시작하면 메뉴 없이 위 흐름을
자동 실행합니다. (`local-ai-launcher.exe setup` 또는 `--setup` 인자로도
같은 동작이 가능합니다.)

### 배포 패키지 만들기

```powershell
# 1) launcher 빌드 + 패키지 폴더/zip 생성
pwsh -File .\scripts\package-release.ps1
```

산출물:

```
dist/
├─ LocalAI_Setup/                  ← 사용자에게 그대로 전달 가능
│  ├─ LocalAI_Setup.exe            ← 더블클릭 시 자동 설치
│  ├─ local-ai-launcher.exe        ← 일상 운영용 메뉴 런처
│  ├─ docker-compose.yml
│  ├─ .env.example
│  ├─ QUICKSTART.txt
│  ├─ README.md
│  ├─ backend/ web-ui/ model-server/ ... (서비스 빌드 컨텍스트)
│  ├─ mysql/init/                  (DB 초기화 SQL)
│  ├─ scripts/
│  ├─ data/  models/  logs/        (.gitkeep 만 포함, 첫 실행 시 채워짐)
└─ LocalAI_Setup-<yyyymmdd>.zip   ← 배포용 압축 파일
```

옵션:

| 옵션 | 의미 |
| --- | --- |
| `-SkipBuild` | launcher 재빌드 없이 기존 `dist/*.exe` 만 패키징 |
| `-NoZip`     | zip 파일 생성을 건너뛰고 폴더만 만든다 |
| `-Version v` | zip 파일명에 들어갈 버전 문자열 (기본: 오늘 날짜) |

### 사용자 입장에서의 흐름

1. zip 다운로드 → 압축 해제
2. `LocalAI_Setup.exe` 더블클릭
3. 설치/기동이 끝나면 자동으로 브라우저가 열리고 LocalAI 사용 시작
4. 다음 실행부터는 `local-ai-launcher.exe` 의 메뉴(`[2] 실행` 등) 사용
