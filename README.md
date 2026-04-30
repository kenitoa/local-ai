# local-ai

> 온디바이스(On-device) AI 플랫폼 — **Step 1: 프로젝트 기본 구조 (초안)**

이 문서는 1단계의 산출물이며, 전체 폴더 구조 / 포트 / 저장 경로 / Docker 볼륨 / MySQL 계정 / `.env` / 로그 정책의 **결정 사항**을 정리합니다.

---

## 1. 결정 사항 (Step 1 체크리스트)

| 항목 | 결정 값 |
|---|---|
| 전체 서비스 이름 | `local-ai` (Compose project name 동일) |
| Docker 네트워크 | `local-ai-net` (bridge) |
| 로컬 데이터 저장 위치 | `./data` (호스트) → 컨테이너 `/app/data` |
| 모델 저장 위치 | `./models` (호스트) → 컨테이너 `/app/models` |
| Docker 볼륨 | `local-ai-mysql-data`, `local-ai-models`, `local-ai-data` |
| MySQL DB | `localai_db` |
| MySQL 계정 | `localai` / 비밀번호는 `.env` |
| `.env` 구조 | `.env.example` 복사 사용 (공통 / 경로 / 포트 / MySQL / 모델 / 로깅 섹션) |
| 로그 저장 방식 | 호스트 `./logs/<서비스명>/` 디렉터리 마운트, 일자별 회전, 14일 보존 |

### 포트 번호

| 서비스 | 포트 |
|---|---|
| web-ui | `3000` |
| backend | `8000` |
| model-server (LLM) | `8001` |
| vision-server | `8002` |
| embedding-server | `8003` |
| language-worker | `8004` |
| hardware-detector | `8005` |
| mysql | `3306` |

---

## 2. 폴더 구조

```
local-ai/
├─ launcher/             # 데스크톱/CLI 런처 (이후 단계)
├─ docker/               # 공용 Dockerfile / compose override
├─ backend/              # API 게이트웨이 (FastAPI 등)
├─ web-ui/               # 프론트엔드
├─ model-server/         # LLM 추론 서버
├─ vision-server/        # 비전(이미지/영상) 추론 서버
├─ embedding-server/     # 임베딩/벡터 서버
├─ language-worker/      # STT/TTS/번역 등 언어 워커
├─ hardware-detector/    # GPU/CPU/메모리 감지
├─ mysql/
│  └─ init/              # 초기 SQL 스크립트
├─ data/                 # 사용자/앱 데이터 (호스트 마운트)
├─ models/               # 모델 가중치 (호스트 마운트)
├─ scripts/              # 유틸리티 스크립트
├─ logs/                 # 서비스별 로그
│  ├─ backend/
│  ├─ web-ui/
│  ├─ model-server/
│  ├─ vision-server/
│  ├─ embedding-server/
│  ├─ language-worker/
│  ├─ hardware-detector/
│  └─ mysql/
├─ docker-compose.yml
├─ .env.example
└─ README.md
```

---

## 3. 빠른 시작

```powershell
# 1) 환경 파일 준비
Copy-Item .env.example .env
# .env 안의 비밀번호/시크릿을 변경하세요.

# 2) (이후 단계) 빌드 & 기동
docker compose build
docker compose up -d
```

> 현재 단계에서는 각 서비스 디렉터리가 placeholder(`.gitkeep`)만 포함합니다. `docker compose build`는 Dockerfile이 추가된 이후에 동작합니다.

---

## 4. 로그 정책

- 모든 서비스는 컨테이너 내부 `/app/logs` (mysql은 `/var/log/mysql`)에 로그를 기록.
- 호스트 `./logs/<서비스>/`에 마운트되어 영구 저장.
- 회전: 일자별(`LOG_ROTATION=daily`) / 보존: `LOG_RETENTION_DAYS=14` (기본값, `.env`로 조정).
- 로그 레벨은 `LOG_LEVEL` (기본 `INFO`)로 통제.

---

## 5. 다음 단계 예고

- Step 2: 각 서비스 Dockerfile 및 최소 동작 코드 추가
- Step 3: 모델 다운로드/관리 스크립트
- Step 4: 하드웨어 감지 → 모델 자동 선택 로직
- Step 5: 런처 / 배포 패키징
