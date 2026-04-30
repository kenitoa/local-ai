-- =====================================================
-- local-ai 핵심 스키마 (Step 4)
-- 흐름: 사용자 입력 저장 → 모델 답변 저장 → embedding 저장
--       → 유사 답변 검색 → 재사용 기록 저장
--
-- 우선순위 높은 테이블:
--   raw_inputs, image_data, model_answers, embeddings,
--   answer_reuse_logs, hardware_profiles
--
-- 참고:
--   - MySQL 8.0 기준, utf8mb4 / InnoDB 사용
--   - vector 컬럼은 JSON(부동소수 배열)로 저장하고
--     필요 시 애플리케이션 레벨에서 코사인 유사도 계산
--   - 큰 바이너리(이미지)는 LONGBLOB 또는 외부 경로 모두 지원
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) projects : 요청을 묶는 단위(선택적 그룹)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(255)    NOT NULL,
  description   TEXT            NULL,
  language      VARCHAR(64)     NULL COMMENT '주 언어(예: python, cpp)',
  created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_projects_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 2) hardware_profiles : 실행 환경(하드웨어) 프로필
--    - hardware-detector 서비스가 채움
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS hardware_profiles (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  host_name       VARCHAR(255)    NULL,
  os_name         VARCHAR(64)     NULL,
  os_version      VARCHAR(64)     NULL,
  cpu_model       VARCHAR(255)    NULL,
  cpu_cores       INT UNSIGNED    NULL,
  ram_mb          INT UNSIGNED    NULL,
  gpu_model       VARCHAR(255)    NULL,
  gpu_vram_mb     INT UNSIGNED    NULL,
  accelerator     VARCHAR(64)     NULL COMMENT 'cuda/rocm/mps/cpu 등',
  fingerprint     CHAR(64)        NOT NULL COMMENT 'sha256 of normalized profile',
  details_json    JSON            NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_hw_fingerprint (fingerprint)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 3) language_profiles : 지원 언어/런타임 프로필
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS language_profiles (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  language        VARCHAR(64)     NOT NULL,
  version         VARCHAR(64)     NULL,
  runtime         VARCHAR(64)     NULL COMMENT '예: cpython, node, jvm',
  package_manager VARCHAR(64)     NULL COMMENT 'pip, npm, cargo 등',
  notes           TEXT            NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_lang_ver (language, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 4) library_patterns : 자주 사용되는 라이브러리/패턴 카탈로그
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS library_patterns (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  language        VARCHAR(64)     NOT NULL,
  library_name    VARCHAR(255)    NOT NULL,
  pattern_name    VARCHAR(255)    NOT NULL,
  pattern_code    MEDIUMTEXT      NULL,
  description     TEXT            NULL,
  tags            JSON            NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_libpat_lang_lib (language, library_name),
  KEY idx_libpat_name (pattern_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 5) training_sources : 학습/참조 데이터 출처
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS training_sources (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_type     VARCHAR(32)     NOT NULL COMMENT 'doc/url/file/dataset',
  title           VARCHAR(512)    NULL,
  uri             VARCHAR(1024)   NULL,
  license         VARCHAR(128)    NULL,
  fetched_at      TIMESTAMP       NULL,
  hash_sha256     CHAR(64)        NULL,
  meta_json       JSON            NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_src_hash (hash_sha256),
  KEY idx_src_type (source_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 6) raw_inputs : 사용자 입력 원본 (텍스트/이미지 첨부 가능)
--    - 흐름의 시작점
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_inputs (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id      BIGINT UNSIGNED NULL,
  hardware_id     BIGINT UNSIGNED NULL,
  language_id     BIGINT UNSIGNED NULL,
  input_type      VARCHAR(32)     NOT NULL DEFAULT 'text'
                                  COMMENT 'text/image/mixed',
  raw_text        MEDIUMTEXT      NULL,
  user_tag        VARCHAR(255)    NULL,
  meta_json       JSON            NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_raw_project (project_id),
  KEY idx_raw_created (created_at),
  CONSTRAINT fk_raw_project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
  CONSTRAINT fk_raw_hardware
    FOREIGN KEY (hardware_id) REFERENCES hardware_profiles(id) ON DELETE SET NULL,
  CONSTRAINT fk_raw_language
    FOREIGN KEY (language_id) REFERENCES language_profiles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 7) image_data : 입력에 첨부된 이미지(원본 또는 경로)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS image_data (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_input_id    BIGINT UNSIGNED NOT NULL,
  mime_type       VARCHAR(64)     NOT NULL DEFAULT 'image/png',
  file_path       VARCHAR(1024)   NULL COMMENT '/app/data 하위 상대경로',
  file_size       INT UNSIGNED    NULL,
  width           INT UNSIGNED    NULL,
  height          INT UNSIGNED    NULL,
  sha256          CHAR(64)        NULL,
  blob_data       LONGBLOB        NULL COMMENT '인라인 저장 시 사용(선택)',
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_img_raw (raw_input_id),
  KEY idx_img_sha (sha256),
  CONSTRAINT fk_img_raw
    FOREIGN KEY (raw_input_id) REFERENCES raw_inputs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 8) extracted_code : 이미지/입력에서 OCR/파싱으로 뽑아낸 코드
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS extracted_code (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_input_id    BIGINT UNSIGNED NOT NULL,
  image_id        BIGINT UNSIGNED NULL,
  language        VARCHAR(64)     NULL,
  code_text       MEDIUMTEXT      NOT NULL,
  ocr_engine      VARCHAR(64)     NULL,
  ocr_confidence  DECIMAL(5,4)    NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_excode_raw (raw_input_id),
  CONSTRAINT fk_excode_raw
    FOREIGN KEY (raw_input_id) REFERENCES raw_inputs(id) ON DELETE CASCADE,
  CONSTRAINT fk_excode_image
    FOREIGN KEY (image_id) REFERENCES image_data(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 9) requirements : 정제된 요구사항(요약/체크리스트)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS requirements (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_input_id    BIGINT UNSIGNED NOT NULL,
  project_id      BIGINT UNSIGNED NULL,
  summary         TEXT            NOT NULL,
  details_json    JSON            NULL,
  priority        TINYINT UNSIGNED NOT NULL DEFAULT 3 COMMENT '1(high)~5(low)',
  status          VARCHAR(32)     NOT NULL DEFAULT 'open',
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_req_raw (raw_input_id),
  KEY idx_req_project (project_id),
  CONSTRAINT fk_req_raw
    FOREIGN KEY (raw_input_id) REFERENCES raw_inputs(id) ON DELETE CASCADE,
  CONSTRAINT fk_req_project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 10) model_answers : 모델이 생성한 응답
--     - 흐름의 두 번째 단계(모델 답변 저장)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS model_answers (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_input_id        BIGINT UNSIGNED NOT NULL,
  requirement_id      BIGINT UNSIGNED NULL,
  model_name          VARCHAR(255)    NOT NULL,
  model_provider      VARCHAR(64)     NULL COMMENT 'local/llama.cpp/ollama 등',
  prompt_text         MEDIUMTEXT      NULL,
  answer_text         MEDIUMTEXT      NOT NULL,
  tokens_input        INT UNSIGNED    NULL,
  tokens_output       INT UNSIGNED    NULL,
  latency_ms          INT UNSIGNED    NULL,
  hardware_id         BIGINT UNSIGNED NULL,
  reused_from_answer_id BIGINT UNSIGNED NULL COMMENT '재사용 기반 답변일 때',
  status              VARCHAR(32)     NOT NULL DEFAULT 'ok',
  created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_ma_raw (raw_input_id),
  KEY idx_ma_req (requirement_id),
  KEY idx_ma_model (model_name),
  KEY idx_ma_created (created_at),
  CONSTRAINT fk_ma_raw
    FOREIGN KEY (raw_input_id) REFERENCES raw_inputs(id) ON DELETE CASCADE,
  CONSTRAINT fk_ma_req
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE SET NULL,
  CONSTRAINT fk_ma_hardware
    FOREIGN KEY (hardware_id) REFERENCES hardware_profiles(id) ON DELETE SET NULL,
  CONSTRAINT fk_ma_reused
    FOREIGN KEY (reused_from_answer_id) REFERENCES model_answers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 11) generated_code : 답변에서 추출/생성된 코드
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS generated_code (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  answer_id       BIGINT UNSIGNED NOT NULL,
  language        VARCHAR(64)     NULL,
  file_name       VARCHAR(255)    NULL,
  code_text       MEDIUMTEXT      NOT NULL,
  is_runnable     TINYINT(1)      NOT NULL DEFAULT 0,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_gc_answer (answer_id),
  CONSTRAINT fk_gc_answer
    FOREIGN KEY (answer_id) REFERENCES model_answers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 12) optimized_code : 사용자/시스템이 최적화한 결과
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS optimized_code (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  generated_code_id   BIGINT UNSIGNED NOT NULL,
  optimizer           VARCHAR(64)     NULL COMMENT 'human/auto/agent명',
  language            VARCHAR(64)     NULL,
  code_text           MEDIUMTEXT      NOT NULL,
  improvement_notes   TEXT            NULL,
  benchmark_json      JSON            NULL,
  created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_oc_gc (generated_code_id),
  CONSTRAINT fk_oc_gc
    FOREIGN KEY (generated_code_id) REFERENCES generated_code(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 13) embeddings : 텍스트/코드에 대한 임베딩 벡터
--     - 흐름의 세 번째 단계(embedding 저장)
--     - target_type/target_id 로 다양한 대상 참조
--     - vector 는 JSON 배열(float)로 저장
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  target_type     VARCHAR(32)     NOT NULL
                    COMMENT 'raw_input/requirement/model_answer/generated_code/extracted_code',
  target_id       BIGINT UNSIGNED NOT NULL,
  model_name      VARCHAR(255)    NOT NULL,
  dim             INT UNSIGNED    NOT NULL,
  vector_json     JSON            NOT NULL COMMENT 'float 배열',
  norm            DOUBLE          NULL COMMENT '사전 계산된 L2 norm(코사인용)',
  content_hash    CHAR(64)        NULL COMMENT '원문 sha256 (중복 방지)',
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_emb_target_model (target_type, target_id, model_name),
  KEY idx_emb_hash (content_hash),
  KEY idx_emb_model (model_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 14) answer_reuse_logs : 유사 답변 재사용 기록
--     - 흐름의 네/다섯 번째 단계
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS answer_reuse_logs (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_input_id        BIGINT UNSIGNED NOT NULL COMMENT '새 입력',
  matched_answer_id   BIGINT UNSIGNED NOT NULL COMMENT '재사용된 기존 답변',
  new_answer_id       BIGINT UNSIGNED NULL     COMMENT '재사용 후 저장된 새 답변(있으면)',
  similarity          DECIMAL(6,5)    NOT NULL COMMENT '코사인 등 유사도',
  metric              VARCHAR(32)     NOT NULL DEFAULT 'cosine',
  embedding_model     VARCHAR(255)    NULL,
  decision            VARCHAR(32)     NOT NULL DEFAULT 'reused'
                        COMMENT 'reused/partial/rejected',
  notes               TEXT            NULL,
  created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_arl_raw (raw_input_id),
  KEY idx_arl_matched (matched_answer_id),
  KEY idx_arl_new (new_answer_id),
  CONSTRAINT fk_arl_raw
    FOREIGN KEY (raw_input_id) REFERENCES raw_inputs(id) ON DELETE CASCADE,
  CONSTRAINT fk_arl_matched
    FOREIGN KEY (matched_answer_id) REFERENCES model_answers(id) ON DELETE CASCADE,
  CONSTRAINT fk_arl_new
    FOREIGN KEY (new_answer_id) REFERENCES model_answers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 15) execution_logs : 생성/최적화된 코드 실행 결과
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS execution_logs (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  generated_code_id   BIGINT UNSIGNED NULL,
  optimized_code_id   BIGINT UNSIGNED NULL,
  hardware_id         BIGINT UNSIGNED NULL,
  language_id         BIGINT UNSIGNED NULL,
  exit_code           INT             NULL,
  duration_ms         INT UNSIGNED    NULL,
  stdout_text         MEDIUMTEXT      NULL,
  stderr_text         MEDIUMTEXT      NULL,
  metrics_json        JSON            NULL,
  status              VARCHAR(32)     NOT NULL DEFAULT 'unknown',
  created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_el_gc (generated_code_id),
  KEY idx_el_oc (optimized_code_id),
  KEY idx_el_status (status),
  CONSTRAINT fk_el_gc
    FOREIGN KEY (generated_code_id) REFERENCES generated_code(id) ON DELETE SET NULL,
  CONSTRAINT fk_el_oc
    FOREIGN KEY (optimized_code_id) REFERENCES optimized_code(id) ON DELETE SET NULL,
  CONSTRAINT fk_el_hw
    FOREIGN KEY (hardware_id) REFERENCES hardware_profiles(id) ON DELETE SET NULL,
  CONSTRAINT fk_el_lang
    FOREIGN KEY (language_id) REFERENCES language_profiles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 스키마 버전 기록(향후 마이그레이션 추적용)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_versions (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  version     VARCHAR(32)  NOT NULL,
  applied_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  note        VARCHAR(255) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_schema_version (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step4', 'Step 4: core schema (inputs/answers/embeddings/reuse)');
