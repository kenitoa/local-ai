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

---

## 6. Step 5 — 로컬 파일 저장 구조

DB(MySQL)에는 **메타데이터만** 저장하고, 실제 파일은 호스트 `./data/`
(컨테이너 `/app/data`) 하위에 카테고리별로 저장합니다.

### 6.1 디렉토리 구조

```
data/
├─ image_data/
│  ├─ original/         # 사용자가 업로드한 이미지 원본
│  ├─ extracted_text/   # 이미지에서 추출한 일반 텍스트
│  ├─ extracted_code/   # 이미지에서 추출한 코드
│  ├─ extracted_spec/   # 이미지에서 추출한 요구사항/스펙
│  └─ metadata/         # EXIF/추출 결과 메타 JSON
├─ code_data/
│  ├─ original/         # 사용자가 입력/업로드한 원본 코드
│  ├─ generated/        # 모델이 생성한 코드
│  ├─ optimized/        # 최적화된 코드
│  └─ diff/             # generated → optimized 의 unified diff
├─ model_answers/       # LLM 답변 원문(.md)
├─ embeddings/          # 임베딩 벡터(.npy / .json)
└─ logs/                # 백엔드 자체 작업 로그
```

### 6.2 DB ↔ 파일 경로 연결

`mysql/init/03_step5_paths.sql` 마이그레이션이 다음 컬럼을 추가합니다.
모두 `DATA_DIR` 기준 **상대 경로**(슬래시 표기)를 저장합니다.

| 테이블 | 추가된 경로 컬럼 |
|---|---|
| `image_data` | `text_file_path`, `code_file_path`, `spec_file_path`, `metadata_file_path` |
| `extracted_code` | `file_path`, `file_size`, `sha256` |
| `raw_inputs` | `source_file_path` |
| `model_answers` | `answer_file_path`, `file_size`, `sha256` |
| `generated_code` | `file_path`, `file_size`, `sha256` |
| `optimized_code` | `file_path`, `diff_file_path`, `file_size`, `sha256` |
| `embeddings` | `vector_file_path`, `file_size`, `sha256` (기존 `vector_json` 은 NULL 허용) |

### 6.3 파일 저장 유틸리티

`backend/storage.py` 모듈이 모든 카테고리에 대해 표준 함수를 제공합니다.

- `save_image_original(data, raw_input_id=..., original_filename=..., mime_type=...)`
- `save_image_extracted_text(text, image_id=...)`
- `save_image_extracted_code(code, image_id=..., language=...)`
- `save_image_extracted_spec(text, image_id=...)`
- `save_image_metadata(meta_dict, image_id=...)`
- `save_original_code(code, raw_input_id=..., language=..., file_name=...)`
- `save_generated_code(code, answer_id=..., language=..., file_name=...)`
- `save_optimized_code(code, generated_code_id=..., language=..., file_name=...)`
- `save_code_diff(diff_text, generated_code_id=..., optimized_code_id=...)`
- `save_model_answer(text, answer_id=..., model_name=...)`
- `save_embedding(vector, target_type=..., target_id=..., model_name=...)`

각 함수는 `SavedFile` 데이터클래스(`rel_path`, `abs_path`, `size`, `sha256`)를
반환하며, `rel_path` 를 그대로 DB `*_file_path` 컬럼에 저장합니다.
파일명은 `<UTC타임스탬프>_<owner_id>_<sanitized_stem>_<short-uuid>.<ext>` 형식이라
충돌이 발생하지 않습니다.

### 6.4 백엔드 API

`backend/app.py` 가 다음 엔드포인트를 노출합니다 (`http://localhost:8000`).

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/uploads/image` | 이미지 원본 업로드 → `raw_inputs` + `image_data` 생성 |
| POST | `/api/v1/images/{image_id}/extracted` | 이미지 추출 텍스트/코드/스펙/메타 저장 |
| POST | `/api/v1/model-answers` | LLM 답변 저장(텍스트 + .md 파일) |
| POST | `/api/v1/generated-code` | 생성 코드 저장 |
| POST | `/api/v1/optimized-code` | 최적화 코드 + diff 자동 생성/저장 |
| POST | `/api/v1/embeddings` | 임베딩 벡터를 .npy 로 저장 |
| GET  | `/api/v1/storage/info` | 카테고리별 파일 개수 / 경로 점검 |
| GET  | `/health` | 서비스 + MySQL 연결 상태 |

### 6.5 체크리스트

- [x] 이미지 원본 저장 (`data/image_data/original/`)
- [x] 이미지 추출 텍스트 저장 (`data/image_data/extracted_text/`)
- [x] 이미지 추출 코드 저장 (`data/image_data/extracted_code/`)
- [x] 생성 코드 저장 (`data/code_data/generated/`)
- [x] 최적화 코드 저장 (`data/code_data/optimized/` + `diff/`)
- [x] 모델 답변 저장 (`data/model_answers/`)
- [x] DB record 와 파일 경로 연결 (`*_file_path` 컬럼 + `mysql/init/03_step5_paths.sql`)
