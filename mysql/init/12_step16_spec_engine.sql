-- =====================================================
-- local-ai Step 16 마이그레이션
--   목적: "명세서 기반 SW 생성 엔진" - 이미지/텍스트 명세서를 받아
--          SW 구조(기능/화면/API/DB/규칙)와 코드까지 한 번에 만든다.
--
--   사진 명세 흐름:
--     명세서 입력 → 요구사항 추출 → 기능 목록 생성 → 화면 목록 생성
--       → API 목록 생성 → DB 테이블 초안 생성 → 프로젝트 구조 생성 → 코드 생성
--
--   사진 중간 데이터(JSON):
--     {
--       "project_name": "...",
--       "features": [],
--       "screens": [],
--       "apis": [],
--       "database_tables": [],
--       "business_rules": []
--     }
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) spec_engine_runs : 명세서 → SW 생성 엔진 실행 이력
--    - 한 행에 사진의 8단계 산출물(JSON)이 모두 보존된다.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS spec_engine_runs (
  id                     INT           NOT NULL AUTO_INCREMENT,
  raw_input_id           INT           NULL,
  project_id             INT           NULL,
  source_kind            ENUM('text','image','file','mixed')
                                       NOT NULL DEFAULT 'text',
  source_image_id        INT           NULL,
  spec_text              MEDIUMTEXT    NULL  COMMENT '입력 명세 원문(또는 OCR 텍스트)',
  spec_file_path         VARCHAR(1024) NULL  COMMENT 'data/spec_engine/input/* 경로',
  project_name           VARCHAR(255)  NULL,
  target_language        VARCHAR(48)   NULL  COMMENT '예: python, typescript',
  target_framework       VARCHAR(64)   NULL  COMMENT '예: fastapi, express, spring',

  requirements_json      JSON          NULL  COMMENT '사진의 "요구사항 추출" 박스',
  intermediate_json      JSON          NULL  COMMENT '사진의 중간 JSON 전체 (project_name + 5 lists)',
  features_json          JSON          NULL,
  screens_json           JSON          NULL,
  apis_json              JSON          NULL,
  database_tables_json   JSON          NULL,
  business_rules_json    JSON          NULL,
  project_structure_json JSON          NULL  COMMENT '사진의 "프로젝트 구조 생성" 박스',
  intermediate_file_path VARCHAR(1024) NULL,

  llm_model              VARCHAR(255)  NULL,
  llm_latency_ms         INT UNSIGNED  NULL,
  total_latency_ms       INT UNSIGNED  NULL,
  feature_count          INT UNSIGNED  NOT NULL DEFAULT 0,
  screen_count           INT UNSIGNED  NOT NULL DEFAULT 0,
  api_count              INT UNSIGNED  NOT NULL DEFAULT 0,
  table_count            INT UNSIGNED  NOT NULL DEFAULT 0,
  rule_count             INT UNSIGNED  NOT NULL DEFAULT 0,
  file_count             INT UNSIGNED  NOT NULL DEFAULT 0,
  status                 ENUM('ok','partial','failed') NOT NULL DEFAULT 'ok',
  notes                  VARCHAR(512)  NULL,
  created_at             TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_specrun_raw     (raw_input_id),
  KEY idx_specrun_project (project_id),
  KEY idx_specrun_image   (source_image_id),
  KEY idx_specrun_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 2) spec_engine_files : 엔진이 생성한 프로젝트의 개별 파일
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS spec_engine_files (
  id              INT           NOT NULL AUTO_INCREMENT,
  run_id          INT           NOT NULL,
  rel_path        VARCHAR(512)  NOT NULL  COMMENT '프로젝트 루트 기준 상대 경로 (예: app/main.py)',
  language        VARCHAR(48)   NULL,
  role            ENUM('backend','frontend','db','config','docs','test','other')
                                NOT NULL DEFAULT 'other',
  code_text       MEDIUMTEXT    NULL,
  file_path       VARCHAR(1024) NULL  COMMENT 'data/spec_engine/project/* 실제 저장 경로',
  file_size       INT UNSIGNED  NULL,
  sha256          CHAR(64)      NULL,
  created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_specfile_run (run_id),
  CONSTRAINT fk_specfile_run
    FOREIGN KEY (run_id) REFERENCES spec_engine_runs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 3) spec_engine_steps : 단계별 산출물 (감사/디버그용)
--    사진의 8개 단계를 row 로 풀어서 보존한다.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS spec_engine_steps (
  id          INT           NOT NULL AUTO_INCREMENT,
  run_id      INT           NOT NULL,
  step_no     TINYINT UNSIGNED NOT NULL,
  step_key    VARCHAR(48)   NOT NULL
    COMMENT 'spec_input / requirements / features / screens / apis / database_tables / project_structure / code_generation',
  label       VARCHAR(128)  NOT NULL,
  output_json JSON          NULL,
  source      ENUM('llm','rule','reuse','user') NOT NULL DEFAULT 'rule',
  llm_model   VARCHAR(255)  NULL,
  latency_ms  INT UNSIGNED  NULL,
  status      ENUM('ok','partial','failed') NOT NULL DEFAULT 'ok',
  notes       VARCHAR(512)  NULL,
  created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_specstep_run (run_id),
  KEY idx_specstep_key (step_key),
  CONSTRAINT fk_specstep_run
    FOREIGN KEY (run_id) REFERENCES spec_engine_runs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step16',
        'Step 16: spec-to-software generation engine (spec → requirements → features → screens → apis → tables → structure → code)');
