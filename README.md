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

---

## 6. Step 17 — 전체 통합 테스트

사진 17단계 흐름(`.exe → Docker Compose → Web UI → Backend → MySQL / Hardware
Detector / Language Worker / Vision Server / LLM Server / Embedding Server`)을
한 번에 점검할 수 있는 시나리오 러너가 추가됐습니다.

### 시나리오 (사진 체크리스트와 1:1)

1. `.exe` 실행
2. Docker Compose 자동 실행
3. Web UI 자동 오픈
4. 코드 입력
5. 모델 답변 생성
6. 답변 저장
7. embedding 저장
8. 같은 요구사항 재입력
9. 기존 답변 재사용
10. 코드 이미지 업로드
11. 이미지에서 코드 추출
12. 추출 코드 기반 답변 생성
13. GPU 없을 때 CPU fallback 확인

### 사용 방법

- **Web UI**: 좌측 사이드바의 `8 통합 테스트` 화면에서 `전체 시나리오 실행`
  버튼을 누르면 13개 시나리오를 순차 실행하고 통과/실패/스킵 상태를 표 형태로
  보여줍니다. 각 행을 클릭하면 단계별 evidence(answer_id, image_id, embedding 등)
  JSON 을 확인할 수 있습니다.
- **API**:
  - `GET  /api/integration/checklist` — 시나리오 카탈로그
  - `POST /api/integration/run` — 전체 시나리오 실행 (DB 기록)
  - `GET  /api/integration/runs` — 실행 이력
  - `GET  /api/integration/runs/{id}` — 실행 상세 + 단계별 결과

### 저장 위치

- MySQL: `integration_runs`, `integration_steps`
  (`mysql/init/13_integration.sql` 마이그레이션으로 자동 생성)
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

`mysql/init/03_paths.sql` 마이그레이션이 다음 컬럼을 추가합니다.
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
- [x] DB record 와 파일 경로 연결 (`*_file_path` 컬럼 + `mysql/init/03_paths.sql`)


---

## 7. Step 7 ? Web UI (�ܼ� SPA)

`web-ui` �����̳ʴ� nginx �� ���� ������(`index.html`)�� �����ϸ�,
���� ���̵�ٷ� 6���� ȭ���� ��ȯ�ϴ� SPA �����Դϴ�.
��� ������/�� ȣ���� `backend` (`http://localhost:8000`) �� REST API �� ����մϴ�.

### 7.1 �ʼ� ȭ�� (���� ���̵��)

| # | ȭ�� | ���� |
|---|---|---|
| 1 | ��ú��� | ���� ��� / ���� ���� / ���� �亯 �� / ������ ���� �� ��� |
| 2 | �ҽ��ڵ� �Է� | ���/��/�䱸����/�ڵ带 �Է��ϰ� "����" ���� �� �亯 ���� |
| 3 | �̹��� ���ε� | �̹��� ���ε� + (����) �䱸�������� ���� |
| 4 | ��� ȭ�� | �亯 ����, �̹���, ����/���� �ڵ� ��, diff ǥ�� |
| 5 | ����� �亯 �˻� | `model_answers` �ؽ�Ʈ �κ���ġ / �𵨸� ���� �˻� |
| 6 | �ý��� ���� | ���� CPU/GPU ��� + ��� Docker ���� `/health` ���� |

### 7.2 �ּ� ��� üũ����Ʈ

- [x] �ڵ� �Է� (`�ҽ��ڵ� �Է�` ȭ��)
- [x] �̹��� ���ε� (`�̹��� ���ε�` ȭ��)
- [x] �䱸���� �Է� (�ڵ�/�̹��� ȭ�� ����)
- [x] ���� ��ư (`POST /api/v1/run` ȣ��)
- [x] ��� ��� (�亯 ���� + ��Ÿ������)
- [x] ����/��� �� (��: �Է� �ڵ�, ��: ����/����ȭ �ڵ�, diff)
- [x] ����� �亯 ��ȸ (�˻� / �� Ŭ�� �� ��� ȭ�� �ڵ� �̵�)
- [x] ���� CPU/GPU ��� ǥ�� (���̵�� + ��ú��� + �ý��� ����)
- [x] Docker ���� ���� ǥ�� (`/api/v1/system/services`)

### 7.3 ���� �߰��� �鿣�� API (Step 7)

| �޼��� | ��� | ���� |
|---|---|---|
| POST | `/api/v1/run` | �䱸����/�ڵ�/�̹����� �� ���� �޾� `raw_inputs` + `model_answers` ���� (model-server �� ���� �� �ϸ� stub echo) |
| GET  | `/api/v1/model-answers` | `?q=&model=&limit=&offset=` �˻�/����¡ |
| GET  | `/api/v1/model-answers/{id}` | �亯 + ����� generated/optimized code + �̹��� ���� |
| GET  | `/api/v1/system/services` | backend �� �� ������ `/health` �� ȣ��, run_mode ���� |
| GET  | `/api/v1/files?path=...` | `DATA_DIR` ���� ����� ���� �ٿ�ε� (�̹��� �̸������) |
| GET  | `/api/v1/files/text?path=...` | �ؽ�Ʈ ���� ���� ��ȯ (���� �ڵ�/diff ǥ�ÿ�) |

### 7.4 ��� ���

```powershell
docker compose up -d --build web-ui backend
# ������: http://localhost:3000
```

���� ���̵�ٿ��� ȭ���� �̵��ϰų� URL �ؽ÷� ���� ������ �� �ֽ��ϴ� :
`http://localhost:3000/#dashboard`, `#code-input`, `#image-upload`,
`#result`, `#search`, `#system`.

> Step 7 �� "����" �� `model-server` �� generation API �� ������ �����Ǳ� ������
> stub echo �亯�� ��ȯ�մϴ�. UI/���� ������������ ���� �����ϴ��� �����ϴ� ��
> ����ϼ���. ���� �ܰ迡�� ���� LLM ȣ��� ��ü�˴ϴ�.


---

## 11. Step 11 — 자체 Vision-Language Model 학습 파이프라인

### 11.1 목표

이미지 → **코드 / 텍스트 / 명세 구조 추출** 을 수행하는 자체 VLM 의 학습/추론
파이프라인을 정의한다. 이 단계의 산출물은 두 가지다.

1. 학습 데이터(JSON) 스키마 + 5단계 학습 카탈로그
2. 초기 VLM 파이프라인(코드 영역 탐지 → 텍스트화 → 파일 저장 → LLM 입력)

> 본 단계에서는 실제 모델 가중치를 학습하지 않는다. `vision-server` 의
> `_detect_code_regions` / `_run_ocr` 자리표시 함수만 교체하면 곧바로
> 실제 VLM 으로 승격할 수 있도록 인터페이스만 표준화한다.

### 11.2 학습 데이터 형태

사진의 명세를 그대로 따른다. 한 샘플당 하나의 JSON 파일이
`data/vlm_training/dataset/<stage>/...` 경로에 저장된다.

```json
{
  "image_path": "data/image_data/original/sample.png",
  "image_type": "code_image",
  "expected_text": "...",
  "expected_code": "...",
  "expected_structure": {}
}
```

### 11.3 학습 단계 (5단계)

| stage_no | stage_key         | image_type  | 라벨                |
|---:|---|---|---|
| 1 | `code_image`       | `code`       | 코드 이미지 인식 (초기 VLM 목표) |
| 2 | `error_log_image`  | `error_log`  | 에러 로그 이미지 인식 |
| 3 | `spec_image`       | `tech_spec`  | 명세서 이미지 인식 |
| 4 | `table_structure`  | `db_design`  | 표 구조 인식 |
| 5 | `ui_layout`        | `ui_design`  | UI 화면 구조 인식 |

### 11.4 초기 VLM 파이프라인

```
이미지 안의 소스코드 영역 탐지
        ↓
코드 텍스트화
        ↓
파일 저장
        ↓
LLM 입력으로 전달
```

한 번의 호출(`POST /api/vlm/code-image-pipeline`) 로 전 과정이 실행되며
산출물은 모두 영구 저장된다.

| 단계 | 컴포넌트 | 산출물 |
|---|---|---|
| 영역 탐지 | `vision-server._detect_code_regions` (현재 stub-fullframe) | `vlm_pipeline_runs.detected_regions` |
| 텍스트화 | `vision-server._run_ocr` (현재 stub) | `vlm_pipeline_runs.extracted_text` |
| 파일 저장 | `backend.storage.save_vlm_pipeline_text` | `data/vlm_training/pipeline_output/` + `image_data.code_file_path` |
| LLM 전달 | `backend._generate_with_model` | `model_answers` + `vlm_pipeline_runs.llm_answer_id` |

### 11.5 추가된 데이터베이스 스키마

마이그레이션 `mysql/init/07_vlm_training.sql` 가 생성한다.

| 테이블 | 용도 |
|---|---|
| `vlm_training_stages` | 5단계 카탈로그 (stage_no/stage_key/image_type/label) |
| `vlm_training_samples` | 학습 샘플 메타 + 사진 JSON 스키마 컬럼 |
| `vlm_pipeline_runs` | 초기 파이프라인 실행 이력(영역/텍스트/저장경로/LLM 답변) |

### 11.6 추가된 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET  | `/api/vlm/stages`               | 학습 단계 카탈로그 + 샘플 스키마 + 초기 파이프라인 정보 |
| POST | `/api/vlm/dataset`              | 학습 샘플 등록 (사진의 JSON 스키마 그대로) |
| GET  | `/api/vlm/dataset`              | 단계/타입/split 별 샘플 목록 |
| GET  | `/api/vlm/dataset/{id}`         | 샘플 상세 |
| GET  | `/api/vlm/training-progress`    | 단계별 train/val/test 샘플 수 |
| POST | `/api/vlm/code-image-pipeline`  | 초기 VLM 파이프라인 (탐지→OCR→저장→LLM) |
| GET  | `/api/v1/vlm/stages`            | (vision-server) 단계 카탈로그 |
| POST | `/api/v1/vlm/detect-code-region`| (vision-server) 코드 영역 탐지 + OCR |

### 11.7 저장 경로

`backend.storage` 의 카테고리:

| 카테고리 키 | 경로 |
|---|---|
| `vlm_dataset` | `data/vlm_training/dataset` |
| `vlm_stage_code` ~ `vlm_stage_ui` | `data/vlm_training/dataset/stage_<n>_<key>` |
| `vlm_pipeline_output` | `data/vlm_training/pipeline_output` |

### 11.8 사용 예

```bash
# 1) 학습 샘플 한 건 등록 (사진 JSON 스키마 그대로)
curl -X POST http://localhost:8000/api/vlm/dataset \
  -H 'content-type: application/json' \
  -d '{
        "image_path": "data/image_data/original/sample.png",
        "image_type": "code_image",
        "expected_text": "def add(a,b): return a+b",
        "expected_code": "def add(a,b):\n    return a+b",
        "expected_structure": {"functions": ["add"]}
      }'

# 2) 단계별 진행도
curl http://localhost:8000/api/vlm/training-progress

# 3) 초기 VLM 파이프라인 실행 (image_id 는 /api/input/image 응답값)
curl -X POST http://localhost:8000/api/vlm/code-image-pipeline \
  -H 'content-type: application/json' \
  -d '{"image_id": 1, "forward_to_llm": true,
        "requirement": "이 코드를 설명해줘"}'
```


---

## 12. Step 12 ? ��ü LLM �н� ����������

### 12.1 ��ǥ

������ 12�ܰ踦 �״�� ���� ��ü LLM �� ó������ �н� �� �߷� ����ȭ�Ѵ�.
�� �ܰ迡���� **������/��Ÿ������ ���������� + �߷� API stub** �� ���� ��� �ΰ�,
���� ��ũ������/�� �н��� �ļ� �۾����� ä�� �ִ´�.

| stage_no | stage_key | �� |
|---:|---|---|
| 1  | `tokenizer_design`      | ��ũ������ ���� |
| 2  | `data_format_design`    | �н� ������ ���� ���� |
| 3  | `collect_code_corpus`   | �� �ڵ� corpus ���� |
| 4  | `curate_library_docs`   | ���̺귯�� ����/���� ������ ���� |
| 5  | `build_optimize_pairs`  | �ڵ� ����ȭ pair dataset ���� |
| 6  | `build_spec_to_code`    | �䱸���� �� �ڵ� dataset ���� |
| 7  | `build_code_to_explain` | �ڵ� �� ���� dataset ���� |
| 8  | `pretrain`              | �����н� |
| 9  | `instruction_tuning`    | instruction tuning |
| 10 | `finetune_optimize`     | �ڵ� ����ȭ fine-tuning |
| 11 | `evaluate`              | �� |
| 12 | `serve_inference`       | �߷� ����ȭ |

### 12.2 �н� ������ ���� (������ 1:1)

```json
{
  "language": "python",
  "library": "example_library",
  "task": "optimize_code",
  "input_code": "...",
  "requirement": "...",
  "output_code": "...",
  "explanation": "..."
}
```

`task` �� `{ optimize_code, spec_to_code, explain_code, instruction, pretrain }`.


---

## 14. Step 14 — 답변 재사용 구조

이 프로젝트의 핵심은 모델이 **매번 새로 답하는 것이 아니라, 기존 답변을
재사용하는 것**이다. Step 13 의 임베딩/유사도 검색 위에 다음 흐름을 추가한다.

### 14.1 흐름

```
새 요구사항 입력
      ↓
embedding 생성
      ↓
MySQL embeddings 테이블에서 유사 답변 검색
      ↓
유사도 ≥ threshold 이면 기존 답변 후보 반환
      ↓
LLM 이 기존 답변을 현재 요구사항에 맞게 수정 (adapt)
      ↓
새 답변 저장 + reuse_count++ + answer_reuse_logs 기록
```

### 14.2 마이그레이션 (`mysql/init/10_reuse.sql`)

| 테이블 | 추가 컬럼 |
|---|---|
| `model_answers`      | `reuse_count`, `last_reused_at`, `idx_ma_reuse_count` |
| `answer_reuse_logs`  | `candidates_json`, `adapted`, `adaptation_prompt`, `adaptation_model`, `latency_ms` |
| (view) `model_answer_reuse_stats` | 재사용된 답변 통계 |

### 14.3 백엔드 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/reuse/find-similar` | 유사 요구사항 / 사용자 코드 / 이미지 추출(텍스트·코드) / 모델 답변을 한 번에 검색 |
| POST | `/api/reuse/answer`       | 사진의 전체 흐름 (검색 → adapt → 새 답변 저장 → reuse_count++ → 로그) |
| GET  | `/api/reuse/logs`         | `answer_reuse_logs` 목록 조회 (필터 지원) |
| GET  | `/api/reuse/stats`        | 답변별 `reuse_count` 상위 + decision 통계 |

`/api/reuse/answer` 의 주요 옵션:

- `requirement`, `code`, `code_language` : 새 입력
- `threshold` (기본 0.85) : "유사도 기준"
- `top_k` (기본 5)
- `adapt=False` 면 후보만 반환하고 LLM 호출/저장은 건너뜀
- `record=False` 면 `answer_reuse_logs` 기록 생략

### 14.4 체크리스트

- [x] 유사 요구사항 검색 (`target_type=requirement`)
- [x] 유사 코드 검색 (`target_type=user_code`)
- [x] 유사 이미지 추출 결과 검색 (`target_type=image_text`, `image_code`)
- [x] 유사 답변 검색 (`target_type=model_answer`)
- [x] `model_answers.reuse_count` 증가
- [x] 재사용 로그 저장 (`answer_reuse_logs`, `decision='reused'/'rejected'`)
- [x] 수정된 답변은 새 `model_answers` 행으로 저장 (`reused_from_answer_id` 연결)


### 12.3 �߰��� �����ͺ��̽� ��Ű��

���̱׷��̼� `mysql/init/08_llm_training.sql` �� ���� ���̺��� �����Ѵ�.

| ���̺� | �뵵 |
|---|---|
| `llm_training_stages`  | 12�ܰ� īŻ�α� |
| `llm_tokenizer_configs`| ��ũ������ ���� (BPE/SentencePiece ��) |
| `llm_code_corpus`      | �� �ڵ� corpus |
| `llm_library_examples` | ���̺귯�� ����/����(���� ��) |
| `llm_training_samples` | �н� ���� (���� JSON ��Ű���� 1:1) |
| `llm_training_runs`    | �ܰ躰 �н� ���� �̷� |
| `llm_eval_results`     | �� ���(metric/value) |
| `llm_inference_runs`   | �߷� ȣ�� �̷� (4�� API) |

### 12.4 ���� ���

`backend.storage` �� �ű� ī�װ��� �߰�:

| ī�װ��� Ű | ��ũ ��� |
|---|---|
| `llm_tokenizer`            | `data/llm_training/tokenizer` |
| `llm_corpus`               | `data/llm_training/corpus` (������ `<language>/`) |
| `llm_library`              | `data/llm_training/library` (`<language>/<library>/`) |
| `llm_dataset_optimize`     | `data/llm_training/dataset/optimize_code` |
| `llm_dataset_spec`         | `data/llm_training/dataset/spec_to_code` |
| `llm_dataset_explain`      | `data/llm_training/dataset/explain_code` |
| `llm_dataset_instruction`  | `data/llm_training/dataset/instruction` |
| `llm_dataset_pretrain`     | `data/llm_training/dataset/pretrain` |
| `llm_eval`                 | `data/llm_training/eval` |
| `llm_checkpoints`          | `data/llm_training/checkpoints` |
| `llm_runs`                 | `data/llm_training/runs` |
| `llm_inference`            | `data/llm_training/inference` |

�н� ������ ����ϸ� DB �� + ���� JSON ��Ű���� �״��
`llm_training/dataset/<task>/...` �� �����ȴ�.

### 12.5 �߰��� LLM �߷� API (���� ����)

`model-server` �� 4�� API �� �����Ѵ� (���� stub, �н� �Ϸ� �� ���� �� ȣ��� ��ü):

| �޼��� | ��� | ���� |
|---|---|---|
| POST | `/generate`     | �Ϲ� �ڵ� ���� (requirement / input_code �Է�) |
| POST | `/optimize`     | �Է� �ڵ� ����ȭ �� output_code + explanation |
| POST | `/explain`      | �ڵ� ���� (input_code �� explanation) |
| POST | `/spec-to-code` | �䱸���� �� �ڵ� (requirement �� output_code) |

���� ��Ű���� �н� �����Ϳ� ���ĵȴ�:
`{ endpoint, model, language, library, output_code, explanation, latency_ms, stub }`.

### 12.6 �߰��� �鿣�� API

| �޼��� | ��� | ���� |
|---|---|---|
| GET  | `/api/llm/stages`              | 12�ܰ� īŻ�α� + �ܰ躰 ����/���� ī��Ʈ |
| GET  | `/api/llm/training-progress`   | task/�� ���� ���� + �ֱ� ���� + corpus ��� |
| POST | `/api/llm/dataset`             | �н� ���� ��� (���� JSON �״��) |
| GET  | `/api/llm/dataset`             | ���� �˻� (`?task=&language=&library=&split=`) |
| GET  | `/api/llm/dataset/{id}`        | ���� �� |
| POST | `/api/llm/tokenizer`           | ��ũ������ ���� ��� (JSON config ����) |
| GET  | `/api/llm/tokenizer`           | ��ũ������ ��� |
| POST | `/api/llm/corpus`              | �� �ڵ� corpus ���� ���ε�(�ؽ�Ʈ) |
| GET  | `/api/llm/corpus`              | corpus ��� (`?language=`) |
| POST | `/api/llm/library`             | ���̺귯�� ����/���� ��� |
| GET  | `/api/llm/library`             | ���̺귯�� ��� (`?language=&library=`) |
| POST | `/api/llm/training-runs`       | �ܰ躰 �н� ���� �̷� ��� |
| GET  | `/api/llm/training-runs`       | �н� ���� �̷� ��ȸ |
| POST | `/api/llm/generate`            | model-server `/generate` ���Ͻ� + ȣ�� �̷� ��� |
| POST | `/api/llm/optimize`            | model-server `/optimize` ���Ͻ� + ȣ�� �̷� ��� |
| POST | `/api/llm/explain`             | model-server `/explain` ���Ͻ� + ȣ�� �̷� ��� |
| POST | `/api/llm/spec-to-code`        | model-server `/spec-to-code` ���Ͻ� + ȣ�� �̷� ��� |
| GET  | `/api/llm/inference-runs`      | �߷� ȣ�� �̷� ��ȸ (`?endpoint=`) |

### 12.7 ��� ��

```bash
# 1) �н� ���� ��� (���� JSON �״��)
curl -X POST http://localhost:8000/api/llm/dataset \
  -H 'content-type: application/json' \
  -d '{
        "language": "python",
        "library": "example_library",
        "task": "optimize_code",
        "input_code": "def add(a,b):\n  return a+b",
        "requirement": "Ÿ�� ��Ʈ�� docstring�� �߰��϶�",
        "output_code": "def add(a: int, b: int) -> int:\n    \"\"\"�� ���� ��.\"\"\"\n    return a + b",
        "explanation": "Ÿ�� ��Ʈ�� docstring�� �߰��ߴ�."
      }'

# 2) �ܰ躰 ���� ��Ȳ
curl http://localhost:8000/api/llm/stages
curl http://localhost:8000/api/llm/training-progress

# 3) �߷� (4�� API)
curl -X POST http://localhost:8000/api/llm/optimize \
  -H 'content-type: application/json' \
  -d '{"input_code":"def add(a,b): return a+b","language":"python"}'

curl -X POST http://localhost:8000/api/llm/spec-to-code \
  -H 'content-type: application/json' \
  -d '{"requirement":"�� ���� �޾� ���� ��ȯ�ϴ� �Լ� �ۼ�","language":"python"}'
```

> Step 12 �� �߷� API �� ���� stub ������ ��ȯ�Ѵ�. ���� LLM ����ġ��
> �ܰ� 1~11 (��ũ������ ���� �� corpus ���� �� �����ͼ� ���� �� pretrain ��
> instruction tuning �� ����ȭ fine-tuning �� ��) �� ��ģ �� model-server ��
> �ε�Ǹ�, API �ñ״�ó�� �״�� �����ȴ�.




---

## 15. Step 15 — 코드 최적화 엔진

> "LLM만으로 최적화하지 말고, 규칙 기반 분석도 같이 둬야 합니다."

### 15.1 흐름 (사진 1:1)

```
코드 입력
   ↓
언어 감지       (language-worker)
   ↓
정적 분석       (backend.optimizer 규칙 기반)
   ↓
라이브러리 패턴 검색  (llm_library_examples + LIBRARY_REPLACEMENTS)
   ↓
과거 답변 검색  (embeddings: model_answer + optimized_code)
   ↓
LLM 최적화      (model-server, 규칙 분석 결과를 prompt 에 주입)
   ↓
결과 비교       (라인/문자/적용 유형 + unified diff)
   ↓
저장            (generated_code + optimized_code + optimization_runs)
```

### 15.2 최적화 유형 (9가지)

| key | 라벨 |
|---|---|
| `syntax_error` | 문법 오류 수정 |
| `typo`         | 오탈자 수정 |
| `dead_code`    | 불필요한 코드 제거 |
| `loop`         | 반복문 개선 |
| `memory`       | 메모리 사용량 개선 |
| `library`      | 라이브러리 대체 |
| `algorithm`    | 알고리즘 개선 |
| `readability`  | 가독성 개선 |
| `speed`        | 실행 속도 개선 |

### 15.3 추가된 데이터베이스 스키마

`mysql/init/11_optimize_engine.sql`

| 테이블 | 용도 |
|---|---|
| `optimization_types`    | 9가지 최적화 유형 카탈로그 |
| `optimization_runs`     | 엔진 실행 1회당 한 행 (입력/출력/diff/JSON 산출물) |
| `optimization_findings` | finding 한 건 (`source` ∈ rule/llm/library/reuse) |

### 15.4 추가된 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET  | `/api/optimize/types`             | 9가지 최적화 유형 카탈로그 |
| POST | `/api/optimize/analyze`           | 규칙 기반 정적 분석만 (LLM 호출 없음) |
| POST | `/api/optimize/library-patterns`  | (language, library) 패턴/대체 후보 검색 |
| POST | `/api/optimize/engine`            | 사진 8단계 엔진을 한 번의 호출로 실행 |
| GET  | `/api/optimize/runs`              | 실행 이력 조회 (`?language=&status=&rule_only=`) |
| GET  | `/api/optimize/runs/{id}`         | 실행 상세 + 모든 finding |

### 15.5 사용 예

```bash
# 1) 규칙 기반 분석만 (즉시 결과)
curl -X POST http://localhost:8000/api/optimize/analyze \
  -H 'content-type: application/json' \
  -d '{"code":"import os\nfor i in range(len(items)):\n    print(items[i])\n","language":"python"}'

# 2) 전체 엔진 실행 (규칙 + 라이브러리 + 재사용 + LLM)
curl -X POST http://localhost:8000/api/optimize/engine \
  -H 'content-type: application/json' \
  -d '{
        "code": "import os\nfor i in range(len(items)):\n    print(items[i])\n",
        "language": "python",
        "requirement": "더 빠르고 가독성 좋게 바꿔줘"
      }'

# 3) 규칙만 사용해서 결과 저장 (LLM 비활성화)
curl -X POST http://localhost:8000/api/optimize/engine \
  -H 'content-type: application/json' \
  -d '{"code":"...","language":"python","use_llm":false}'

# 4) 실행 이력 조회
curl http://localhost:8000/api/optimize/runs?limit=10
```

### 15.6 규칙 모듈

`backend/optimizer.py` 가 9가지 유형을 즉시 탐지한다.

- Python 은 `ast.parse` + walker 로 문법 오류 / 미사용 import 까지 잡는다.
- 다른 언어는 정규식·괄호 균형 등 가벼운 휴리스틱.
- `findings_to_prompt_hint()` 가 분석 결과를 한국어 힌트로 직렬화해서
  LLM 프롬프트에 그대로 끼워 넣는다 → "규칙 + LLM" 하이브리드.

### 15.7 체크리스트

- [x] 코드 입력 (`/api/optimize/engine` 의 `code`)
- [x] 언어 감지 (`language-worker` + 사용자 hint)
- [x] 정적 분석 (`optimizer.analyze` — 9가지 유형)
- [x] 라이브러리 패턴 검색 (`llm_library_examples` + 휴리스틱)
- [x] 과거 답변 검색 (`embeddings`: `model_answer` / `optimized_code`)
- [x] LLM 최적화 (`model-server /optimize`, 규칙 결과를 prompt 에 반영)
- [x] 결과 비교 (`optimizer.compare` + unified diff)
- [x] 저장 (`generated_code` + `optimized_code` + `optimization_runs` + `optimization_findings`)


---

## 19. Step 19 — 테스트 / 벤치마크

사진 19단계 체크리스트(시스템 / AI 기능 / 성능)를 한 번의 호출로 평가하고
항목별 통과·실패·N/A 와 측정값(ms) 을 영구 기록한다.

### 19.1 체크리스트 (사진 1:1)

| 분류 | 항목 |
|---|---|
| 시스템 | Windows 10 / Windows 11 / Docker 설치됨 / Docker 미설치 / GPU 있음 / GPU 없음 / RAM 부족 / 저장공간 부족 |
| AI 기능 | 코드 입력 / 코드 이미지 입력 / 에러 이미지 입력 / 명세서 이미지 입력 / 답변 저장 / embedding 저장 / 과거 답변 재사용 / 여러 언어 입력 |
| 성능 | CPU 모드 속도 / GPU 모드 속도 / 이미지 처리 속도 / 답변 생성 속도 / MySQL 검색 속도 / embedding 유사도 검색 속도 |

### 19.2 추가된 데이터베이스 스키마

마이그레이션 `mysql/init/14_benchmark.sql` :

| 테이블 | 용도 |
|---|---|
| `benchmark_runs`  | 벤치마크 1회 실행 (run_mode/OS/통과·실패 카운트/총지연 등) |
| `benchmark_items` | 22개 체크리스트 항목별 결과 (status/value_ms/value_text/evidence) |

상태값:

- `passed`  : 조건 충족 또는 측정 성공 (성능 항목은 `perf_budget_ms` 이하)
- `failed`  : 측정 실패 또는 budget 초과
- `skipped` : 환경상 N/A (예: GPU 없음 환경에서 `GPU 있음` 항목)
- `info`    : 판정 불가 (예: 호스트 OS 정보 부재)

### 19.3 추가된 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET  | `/api/benchmark/checklist`    | 22개 항목 카탈로그 (분류별 그룹) |
| POST | `/api/benchmark/run`          | 전체 실행 + DB 기록 (한 번 호출에 22개 평가) |
| GET  | `/api/benchmark/runs`         | 과거 실행 이력 |
| GET  | `/api/benchmark/runs/{id}`    | 실행 상세 + 항목별 결과 |

`POST /api/benchmark/run` 의 주요 옵션:

- `host_info.os_name` / `host_info.os_version` — 런처가 호스트 OS 를 알려주면
  Windows 10 / 11 분류가 정확해진다 (백엔드 컨테이너에서는 직접 식별 불가).
- `host_info.docker_installed` — Docker 미설치 시나리오를 강제 평가할 때 사용.
- `ram_low_threshold_gb` (기본 8) / `disk_low_threshold_gb` (기본 10)
  — "RAM 부족 / 저장공간 부족" 판정 기준.
- `perf_budget_ms` (기본 5000) — 성능 항목의 통과 기준.

### 19.4 Web UI

좌측 사이드바 `9 테스트 / 벤치마크` 화면에서 `전체 벤치마크 실행` 버튼을
누르면 22개 항목을 순차 실행하고 분류별 표(시스템/AI 기능/성능)에
통과·실패·N/A·info 와 `ms` 측정값을 표시한다. 행을 클릭하면 단계별
evidence(answer_id, image_id, embedding_id 등) JSON 을 볼 수 있고,
`최근 실행 기록` 으로 과거 run 을 다시 표시한다.

### 19.5 사용 예

```bash
# 1) 전체 벤치마크 실행 (런처가 호스트 OS 를 같이 알려주면 가장 정확)
curl -X POST http://localhost:8000/api/benchmark/run \
  -H 'content-type: application/json' \
  -d '{
        "triggered_by": "cli",
        "host_info": {"os_name": "Windows", "os_version": "11"},
        "ram_low_threshold_gb": 8,
        "disk_low_threshold_gb": 10,
        "perf_budget_ms": 5000
      }'

# 2) 특정 항목만 건너뛰기 (예: 이미지 처리는 vision-server 가 placeholder 라 스킵)
curl -X POST http://localhost:8000/api/benchmark/run \
  -H 'content-type: application/json' \
  -d '{"skip_items": ["image_speed", "spec_image_input"]}'

# 3) 카탈로그 / 이력 / 상세
curl http://localhost:8000/api/benchmark/checklist
curl http://localhost:8000/api/benchmark/runs?limit=10
curl http://localhost:8000/api/benchmark/runs/1
```



---

## 20. Step 20 — 최종 배포 구조 완성 (LocalAI_Setup.exe)

사용자가 실제로 설치 가능한 형태로 배포 구조를 완성한 단계입니다.
사진 20단계 흐름을 그대로 구현합니다.

`
사용자 다운로드
   ↓
LocalAI_Setup.exe 실행
   ↓
필수 구성 확인       (Docker Desktop / Compose / .env / 디렉터리 / GPU·CPU)
   ↓
Docker Compose 실행  (up -d --build → health check)
   ↓
브라우저 자동 실행   (기본 브라우저로 http://localhost:WEB_UI_PORT)
   ↓
로컬 AI 사용
`

### 20.1 산출물

| 파일 | 설명 |
| --- | --- |
| `launcher/dist/LocalAI_Setup.exe` | 더블클릭 시 메뉴 없이 위 흐름을 자동 실행하는 설치 진입점 |
| `launcher/dist/local-ai-launcher.exe` | 일상 운영(실행/중지/로그/복구) 메뉴 런처 (Step 18) |
| `dist/LocalAI_Setup/` | 사용자에게 그대로 전달 가능한 폴더 |
| `dist/LocalAI_Setup-<yyyymmdd>.zip` | 위 폴더의 zip 배포본 |

LocalAI_Setup.exe 와 local-ai-launcher.exe 는 **동일 바이너리**이며,
실행 파일 이름이 `LocalAI_Setup` 으로 시작하면 메뉴 없이 자동 설치
모드로 진입합니다 (local-ai-launcher.exe setup 또는 --setup 인자도 동일).

### 20.2 빌드 / 패키징

`powershell
# launcher 빌드 (LocalAI_Setup.exe + local-ai-launcher.exe)
pwsh -File .\launcher\build.ps1

# 배포 폴더 + zip 생성 (위 빌드를 자동으로 호출)
pwsh -File .\scripts\package-release.ps1
`

옵션은 `launcher/README.md` 의 *Step 20 — 최종 배포 구조* 섹션을 참고하세요.

### 20.3 사용자 사용 흐름

1. `LocalAI_Setup-<ver>.zip` 다운로드 → 압축 해제
2. `LocalAI_Setup.exe` 더블클릭
3. 자동으로: 필수 구성 확인 → `docker compose up -d --build` → health check → 브라우저 오픈
4. 다음 실행부터는 `local-ai-launcher.exe` 메뉴(`[2] 실행`) 사용
