-- =====================================================
-- local-ai Step 5 마이그레이션
--   목적: DB record와 로컬 파일 경로 연결
--   - 각 산출물 테이블에 file_path / file_size / sha256 컬럼 추가
--   - 이미지에서 추출한 텍스트/스펙 보관용 테이블 신설
--   - file_path 는 DATA_DIR(./data, 컨테이너에서는 /app/data) 기준 상대 경로
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- image_data : 이미지에서 파생된 텍스트/코드/스펙/메타 파일 경로 컬럼 추가
-- -----------------------------------------------------
ALTER TABLE image_data
  ADD COLUMN IF NOT EXISTS text_file_path     VARCHAR(1024) NULL
    COMMENT 'image_data/extracted_text/* 상대경로',
  ADD COLUMN IF NOT EXISTS code_file_path     VARCHAR(1024) NULL
    COMMENT 'image_data/extracted_code/* 상대경로',
  ADD COLUMN IF NOT EXISTS spec_file_path     VARCHAR(1024) NULL
    COMMENT 'image_data/extracted_spec/* 상대경로',
  ADD COLUMN IF NOT EXISTS metadata_file_path VARCHAR(1024) NULL
    COMMENT 'image_data/metadata/*.json 상대경로';

-- -----------------------------------------------------
-- extracted_code : 이미지에서 추출한 코드 파일 경로
-- -----------------------------------------------------
ALTER TABLE extracted_code
  ADD COLUMN IF NOT EXISTS file_path VARCHAR(1024) NULL
    COMMENT 'image_data/extracted_code/* 상대경로',
  ADD COLUMN IF NOT EXISTS file_size INT UNSIGNED NULL,
  ADD COLUMN IF NOT EXISTS sha256    CHAR(64)     NULL;

-- -----------------------------------------------------
-- raw_inputs : 사용자가 직접 입력/업로드한 코드 원본 경로 (선택)
-- -----------------------------------------------------
ALTER TABLE raw_inputs
  ADD COLUMN IF NOT EXISTS source_file_path VARCHAR(1024) NULL
    COMMENT 'code_data/original/* 상대경로';

-- -----------------------------------------------------
-- model_answers : LLM 답변 원문 저장 경로
-- -----------------------------------------------------
ALTER TABLE model_answers
  ADD COLUMN IF NOT EXISTS answer_file_path VARCHAR(1024) NULL
    COMMENT 'model_answers/*.md 상대경로',
  ADD COLUMN IF NOT EXISTS file_size        INT UNSIGNED  NULL,
  ADD COLUMN IF NOT EXISTS sha256           CHAR(64)      NULL;

-- -----------------------------------------------------
-- generated_code / optimized_code : 코드 본문 파일 경로 + diff
-- -----------------------------------------------------
ALTER TABLE generated_code
  ADD COLUMN IF NOT EXISTS file_path VARCHAR(1024) NULL
    COMMENT 'code_data/generated/* 상대경로',
  ADD COLUMN IF NOT EXISTS file_size INT UNSIGNED NULL,
  ADD COLUMN IF NOT EXISTS sha256    CHAR(64)     NULL;

ALTER TABLE optimized_code
  ADD COLUMN IF NOT EXISTS file_path      VARCHAR(1024) NULL
    COMMENT 'code_data/optimized/* 상대경로',
  ADD COLUMN IF NOT EXISTS diff_file_path VARCHAR(1024) NULL
    COMMENT 'code_data/diff/*.diff 상대경로',
  ADD COLUMN IF NOT EXISTS file_size      INT UNSIGNED  NULL,
  ADD COLUMN IF NOT EXISTS sha256         CHAR(64)      NULL;

-- -----------------------------------------------------
-- embeddings : 벡터를 .npy/.json 파일로도 저장할 수 있도록 경로 컬럼 추가
--   기존 vector_json 은 NULL 허용으로 완화 (둘 중 하나 또는 둘 다 가능)
-- -----------------------------------------------------
ALTER TABLE embeddings
  MODIFY COLUMN vector_json JSON NULL,
  ADD COLUMN IF NOT EXISTS vector_file_path VARCHAR(1024) NULL
    COMMENT 'embeddings/*.npy 또는 *.json 상대경로',
  ADD COLUMN IF NOT EXISTS file_size        INT UNSIGNED  NULL,
  ADD COLUMN IF NOT EXISTS sha256           CHAR(64)      NULL;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step5', 'Step 5: link DB records with local file paths');
