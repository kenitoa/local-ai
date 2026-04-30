-- =====================================================
-- local-ai Step 10 마이그레이션
--   목적: 이미지 입력 처리 구조
--   - image_data 에 이미지 타입 / 분류 신뢰도 / 추출 상태 컬럼 추가
--   - 8가지 이미지 타입을 정의:
--       code         : 코드 스크린샷
--       error_log    : 에러 / 스택트레이스 로그
--       algorithm    : 알고리즘 문제 (백준/리트코드 등)
--       tech_spec    : 기술 명세서 / 설계 문서
--       api_spec     : API 명세 (REST/GraphQL 등)
--       db_design    : DB 설계 (ERD/스키마)
--       ui_design    : UI 설계 (와이어프레임/목업)
--       other        : 기타
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- image_data : 이미지 타입 / 분류 신뢰도 / 추출 상태
-- -----------------------------------------------------
ALTER TABLE image_data
  ADD COLUMN IF NOT EXISTS image_type            VARCHAR(32) NULL
    COMMENT 'code/error_log/algorithm/tech_spec/api_spec/db_design/ui_design/other',
  ADD COLUMN IF NOT EXISTS image_type_source     VARCHAR(16) NULL
    COMMENT 'user/auto/hint',
  ADD COLUMN IF NOT EXISTS image_type_confidence DECIMAL(5,4) NULL,
  ADD COLUMN IF NOT EXISTS extraction_status     VARCHAR(16) NULL DEFAULT 'pending'
    COMMENT 'pending/done/failed/skipped',
  ADD COLUMN IF NOT EXISTS extraction_engine     VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS extracted_at          TIMESTAMP   NULL,
  ADD KEY idx_img_type (image_type),
  ADD KEY idx_img_status (extraction_status);

-- 버전 기록
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step10', 'Step 10: image input pipeline (type classification + per-type extraction)');
