-- =====================================================
-- local-ai Step 12 마이그레이션
--   목적: 자체 LLM 학습 파이프라인
--   - 12단계 카탈로그 (llm_training_stages)
--   - 토크나이저 설계 (llm_tokenizer_configs)
--   - 언어별 코드 corpus (llm_code_corpus)
--   - 라이브러리 문서/예제 (llm_library_examples)
--   - 학습 샘플 (llm_training_samples) : 사진의 JSON 스키마와 1:1
--       {
--         "language": "python",
--         "library": "example_library",
--         "task": "optimize_code",
--         "input_code": "...",
--         "requirement": "...",
--         "output_code": "...",
--         "explanation": "..."
--       }
--   - 학습 실행 이력 (llm_training_runs)
--   - 평가 결과 (llm_eval_results)
--   - 추론 호출 이력 (llm_inference_runs)
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) 학습 단계 카탈로그 (12단계)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_training_stages (
  id            INT          NOT NULL AUTO_INCREMENT,
  stage_no      INT          NOT NULL UNIQUE,
  stage_key     VARCHAR(48)  NOT NULL UNIQUE,
  label         VARCHAR(128) NOT NULL,
  description   VARCHAR(512) NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO llm_training_stages (stage_no, stage_key, label, description) VALUES
  (1,  'tokenizer_design',         '토크나이저 설계',          'BPE/SentencePiece 등 토크나이저 정의'),
  (2,  'data_format_design',       '학습 데이터 포맷 설계',    'language/library/task/input_code/requirement/output_code/explanation 스키마'),
  (3,  'collect_code_corpus',      '언어별 코드 corpus 수집',  '사전학습용 raw 코드 corpus'),
  (4,  'curate_library_docs',      '라이브러리 문서/예제 정제','공식 문서/예제 코드 정제'),
  (5,  'build_optimize_pairs',     '코드 최적화 pair dataset', 'input_code → output_code 최적화 페어'),
  (6,  'build_spec_to_code',       '요구사항 → 코드 dataset',  'requirement → output_code 페어'),
  (7,  'build_code_to_explain',    '코드 → 설명 dataset',      'input_code → explanation 페어'),
  (8,  'pretrain',                 '사전학습',                 'corpus 기반 LM pretrain'),
  (9,  'instruction_tuning',       'instruction tuning',       'instruction → response SFT'),
  (10, 'finetune_optimize',        '코드 최적화 fine-tuning',  'optimize pair 로 SFT'),
  (11, 'evaluate',                 '평가',                     'eval 데이터셋 / 메트릭 산출'),
  (12, 'serve_inference',          '추론 서버화',              '/generate /optimize /explain /spec-to-code 서빙')
ON DUPLICATE KEY UPDATE
  label       = VALUES(label),
  description = VALUES(description);

-- -----------------------------------------------------
-- 2) 토크나이저 설계
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_tokenizer_configs (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  name          VARCHAR(128) NOT NULL UNIQUE,
  algorithm     VARCHAR(32)  NOT NULL DEFAULT 'bpe'
    COMMENT 'bpe / sentencepiece / wordpiece / unigram',
  vocab_size    INT          NOT NULL DEFAULT 32000,
  special_tokens JSON        NULL
    COMMENT '["<pad>","<bos>","<eos>","<unk>","<code>","<lang>","<task>"] 등',
  notes         TEXT         NULL,
  config_file_path VARCHAR(512) NULL
    COMMENT 'data/llm_training/tokenizer/<name>.json 등',
  artifact_file_path VARCHAR(512) NULL
    COMMENT '학습 완료된 vocab/merges 파일 경로',
  is_active     TINYINT(1)   NOT NULL DEFAULT 0,
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 3) 언어별 코드 corpus (사전학습용)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_code_corpus (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  language      VARCHAR(32)  NOT NULL,
  source        VARCHAR(64)  NULL
    COMMENT 'github/local/curated/...',
  source_url    VARCHAR(1024) NULL,
  file_name     VARCHAR(255) NULL,
  file_path     VARCHAR(512) NOT NULL
    COMMENT 'data/llm_training/corpus/<language>/...',
  file_size     INT UNSIGNED NULL,
  sha256        CHAR(64)     NULL,
  license       VARCHAR(64)  NULL,
  token_count   INT          NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'collected'
    COMMENT 'collected/cleaned/rejected',
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_corpus_lang   (language),
  KEY idx_corpus_status (status),
  KEY idx_corpus_sha    (sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 4) 라이브러리 문서/예제 (정제 후)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_library_examples (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  language      VARCHAR(32)  NOT NULL,
  library       VARCHAR(128) NOT NULL,
  version       VARCHAR(32)  NULL,
  topic         VARCHAR(255) NULL
    COMMENT '함수/클래스/주제',
  doc_text      MEDIUMTEXT   NULL,
  example_code  MEDIUMTEXT   NULL,
  source_url    VARCHAR(1024) NULL,
  file_path     VARCHAR(512) NULL
    COMMENT 'data/llm_training/library/<language>/<library>/...',
  status        VARCHAR(16)  NOT NULL DEFAULT 'curated'
    COMMENT 'raw/curated/rejected',
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_lib_lang_lib (language, library),
  KEY idx_lib_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 5) 학습 샘플 (사진의 JSON 스키마와 1:1)
--    task ∈ {optimize_code, spec_to_code, explain_code, instruction, pretrain}
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_training_samples (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  stage_id        INT          NULL
    COMMENT 'llm_training_stages.id (생성된 단계)',
  task            VARCHAR(32)  NOT NULL
    COMMENT 'optimize_code / spec_to_code / explain_code / instruction / pretrain',
  language        VARCHAR(32)  NOT NULL,
  library         VARCHAR(128) NULL,
  input_code      MEDIUMTEXT   NULL,
  requirement     MEDIUMTEXT   NULL,
  output_code     MEDIUMTEXT   NULL,
  explanation     MEDIUMTEXT   NULL,
  meta_json       JSON         NULL
    COMMENT '추가 라벨(난이도/태그/출처 등)',
  sample_file_path VARCHAR(512) NULL
    COMMENT '디스크에 저장된 JSON 샘플 경로',
  split           VARCHAR(16)  NOT NULL DEFAULT 'train'
    COMMENT 'train/val/test',
  source          VARCHAR(32)  NOT NULL DEFAULT 'manual'
    COMMENT 'manual/auto/import/synthetic',
  quality_score   DECIMAL(5,4) NULL,
  status          VARCHAR(16)  NOT NULL DEFAULT 'ready'
    COMMENT 'ready/hold/rejected',
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_sample_task    (task),
  KEY idx_llm_sample_lang    (language),
  KEY idx_llm_sample_library (library),
  KEY idx_llm_sample_split   (split),
  KEY idx_llm_sample_stage   (stage_id),
  CONSTRAINT fk_llm_sample_stage
    FOREIGN KEY (stage_id) REFERENCES llm_training_stages (id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 6) 학습 실행 이력 (단계별)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_training_runs (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  stage_id        INT          NOT NULL,
  stage_key       VARCHAR(48)  NOT NULL,
  run_name        VARCHAR(128) NULL,
  base_model      VARCHAR(128) NULL
    COMMENT '사전학습 결과 / 이전 fine-tune 결과 등',
  tokenizer_id    BIGINT       NULL,
  dataset_filter  JSON         NULL
    COMMENT '학습에 사용한 샘플 필터 (task/language/split 등)',
  hyperparams     JSON         NULL
    COMMENT 'lr/batch/epochs/...',
  status          VARCHAR(16)  NOT NULL DEFAULT 'pending'
    COMMENT 'pending/running/done/failed/cancelled',
  metrics_json    JSON         NULL
    COMMENT 'loss/perplexity/accuracy 등',
  log_file_path   VARCHAR(512) NULL,
  checkpoint_path VARCHAR(512) NULL,
  started_at      TIMESTAMP    NULL,
  finished_at     TIMESTAMP    NULL,
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_run_stage  (stage_id),
  KEY idx_llm_run_status (status),
  CONSTRAINT fk_llm_run_stage
    FOREIGN KEY (stage_id) REFERENCES llm_training_stages (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_llm_run_tokenizer
    FOREIGN KEY (tokenizer_id) REFERENCES llm_tokenizer_configs (id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 7) 평가 결과
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_eval_results (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  training_run_id BIGINT       NULL,
  task            VARCHAR(32)  NOT NULL
    COMMENT 'optimize_code / spec_to_code / explain_code / pretrain',
  metric_name     VARCHAR(64)  NOT NULL
    COMMENT 'pass@1 / bleu / rouge / perplexity / human_eval',
  metric_value    DECIMAL(10,6) NOT NULL,
  sample_count    INT          NULL,
  detail_json     JSON         NULL,
  report_file_path VARCHAR(512) NULL,
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_eval_run  (training_run_id),
  KEY idx_llm_eval_task (task),
  CONSTRAINT fk_llm_eval_run
    FOREIGN KEY (training_run_id) REFERENCES llm_training_runs (id)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 8) 추론 호출 이력 (Step 12 - 추론 서버화)
--    /generate /optimize /explain /spec-to-code 호출 추적
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_inference_runs (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  endpoint        VARCHAR(32)  NOT NULL
    COMMENT 'generate / optimize / explain / spec_to_code',
  model_name      VARCHAR(128) NULL,
  language        VARCHAR(32)  NULL,
  library         VARCHAR(128) NULL,
  input_code      MEDIUMTEXT   NULL,
  requirement     MEDIUMTEXT   NULL,
  output_code     MEDIUMTEXT   NULL,
  explanation     MEDIUMTEXT   NULL,
  raw_response    JSON         NULL,
  latency_ms      INT          NULL,
  status          VARCHAR(16)  NOT NULL DEFAULT 'ok'
    COMMENT 'ok / failed / stub',
  answer_id       BIGINT       NULL
    COMMENT 'model_answers.id (있으면 연결)',
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_inf_endpoint (endpoint),
  KEY idx_llm_inf_model    (model_name),
  KEY idx_llm_inf_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 버전 기록
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step12', 'Step 12: self LLM training pipeline (stages, tokenizer, corpus, library, samples, training runs, eval, inference logs)');
