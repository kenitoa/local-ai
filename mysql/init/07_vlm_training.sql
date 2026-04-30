-- =====================================================
-- local-ai Step 11 마이그레이션
--   목적: 자체 Vision-Language Model 학습 파이프라인
--   - 5단계 학습 카탈로그(vlm_training_stages)
--   - 학습 샘플 메타데이터(vlm_training_samples)
--     스키마는 사진의 JSON 형식과 1:1 매핑한다:
--       image_path / image_type / expected_text /
--       expected_code / expected_structure
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) 학습 단계 카탈로그
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS vlm_training_stages (
  id            INT          NOT NULL AUTO_INCREMENT,
  stage_no      INT          NOT NULL UNIQUE,
  stage_key     VARCHAR(32)  NOT NULL UNIQUE,
  label         VARCHAR(128) NOT NULL,
  image_type    VARCHAR(32)  NOT NULL
    COMMENT 'image_data.image_type 와 동일한 키',
  description   VARCHAR(255) NULL,
  is_initial    TINYINT(1)   NOT NULL DEFAULT 0
    COMMENT '초기 VLM 목표(Stage 1) 여부',
  PRIMARY KEY (id),
  KEY idx_vlm_stage_image_type (image_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO vlm_training_stages (stage_no, stage_key, label, image_type, description, is_initial) VALUES
  (1, 'code_image',      '코드 이미지 인식',        'code',       '코드 스크린샷에서 영역 탐지 + 텍스트화', 1),
  (2, 'error_log_image', '에러 로그 이미지 인식',   'error_log',  '에러/스택트레이스 이미지에서 텍스트화',   0),
  (3, 'spec_image',      '명세서 이미지 인식',      'tech_spec',  '기술/요구사항 명세 이미지 구조 추출',     0),
  (4, 'table_structure', '표 구조 인식',            'db_design',  'ERD/표 구조의 행/열 인식',                0),
  (5, 'ui_layout',       'UI 화면 구조 인식',       'ui_design',  '와이어프레임/목업의 컴포넌트 구조 추출',   0)
ON DUPLICATE KEY UPDATE
  label       = VALUES(label),
  image_type  = VALUES(image_type),
  description = VALUES(description),
  is_initial  = VALUES(is_initial);

-- -----------------------------------------------------
-- 2) 학습 샘플 (사진의 JSON 스키마와 1:1)
--    {
--      "image_path": "data/image_data/original/sample.png",
--      "image_type": "code_image",
--      "expected_text": "...",
--      "expected_code": "...",
--      "expected_structure": {}
--    }
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS vlm_training_samples (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  stage_id            INT          NOT NULL,
  stage_key           VARCHAR(32)  NOT NULL,
  image_type          VARCHAR(32)  NOT NULL
    COMMENT 'code/error_log/algorithm/tech_spec/api_spec/db_design/ui_design/other',
  image_id            BIGINT       NULL
    COMMENT 'image_data.id (있으면 연결)',
  image_path          VARCHAR(512) NOT NULL
    COMMENT 'DATA_DIR 기준 상대 경로 (예: data/image_data/original/sample.png)',
  expected_text       MEDIUMTEXT   NULL,
  expected_code       MEDIUMTEXT   NULL,
  expected_language   VARCHAR(32)  NULL,
  expected_structure  JSON         NULL,
  sample_file_path    VARCHAR(512) NULL
    COMMENT '학습 샘플 JSON 파일 경로 (data/vlm_training/...)',
  split               VARCHAR(16)  NOT NULL DEFAULT 'train'
    COMMENT 'train/val/test',
  source              VARCHAR(32)  NOT NULL DEFAULT 'manual'
    COMMENT 'manual/auto/import',
  user_tag            VARCHAR(64)  NULL,
  notes               VARCHAR(512) NULL,
  created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_vlm_sample_stage   (stage_id),
  KEY idx_vlm_sample_stage_k (stage_key),
  KEY idx_vlm_sample_type    (image_type),
  KEY idx_vlm_sample_split   (split),
  KEY idx_vlm_sample_image   (image_id),
  CONSTRAINT fk_vlm_sample_stage
    FOREIGN KEY (stage_id) REFERENCES vlm_training_stages (id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 3) 초기 VLM 파이프라인(코드 영역 → 텍스트화 → 파일 저장 → LLM 입력)
--    실행 이력 / 산출물 추적
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS vlm_pipeline_runs (
  id                BIGINT       NOT NULL AUTO_INCREMENT,
  image_id          BIGINT       NULL,
  raw_input_id      BIGINT       NULL,
  pipeline          VARCHAR(48)  NOT NULL DEFAULT 'code_region_extract'
    COMMENT 'code_region_extract / error_log_extract / spec_extract / ...',
  detector          VARCHAR(64)  NULL
    COMMENT '영역 탐지 모델 이름 (stub-fullframe / yolo-code / ...)',
  ocr_engine        VARCHAR(64)  NULL,
  region_count      INT          NULL,
  detected_regions  JSON         NULL
    COMMENT '[{"bbox":[x,y,w,h],"score":0.9,"label":"code"}, ...]',
  extracted_text    MEDIUMTEXT   NULL,
  text_file_path    VARCHAR(512) NULL
    COMMENT 'data/image_data/extracted_code/... 등 저장 경로',
  llm_answer_id     BIGINT       NULL
    COMMENT '추출 텍스트를 LLM 으로 보낸 model_answers.id',
  status            VARCHAR(16)  NOT NULL DEFAULT 'done'
    COMMENT 'done/failed/skipped',
  latency_ms        INT          NULL,
  created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_vlm_run_image (image_id),
  KEY idx_vlm_run_pipe  (pipeline)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 버전 기록
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step11', 'Step 11: VLM training pipeline (stages, samples, initial code-region pipeline runs)');
