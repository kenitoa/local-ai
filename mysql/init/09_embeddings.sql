-- =====================================================
-- local-ai Step 13 마이그레이션
--   목적: Embedding 모델과 저장 구조 (답변 재사용의 핵심)
--
--   사진 명세:
--     대상: 요구사항 / 사용자 입력 코드 / 이미지 추출 텍스트 /
--           이미지 추출 코드 / 모델 답변 / 최적화 코드 / 명세서 구조
--     흐름: 입력 저장 → embedding 생성 → MySQL embeddings 테이블 저장
--           → 유사도 검색 → 관련 답변 재사용
--     embeddings 컬럼: embedding_id / target_type / target_id /
--                       model_version / vector_dim / vector_data / created_at
--
--   기존 (Step 4) embeddings 테이블 컬럼은 유지하고,
--   사진 명세 컬럼명을 "view" 로 노출 + 호환 컬럼만 추가한다.
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) embedding_targets : 사진의 7가지 임베딩 대상 카탈로그
--    - 백엔드 /api/embeddings/targets 가 그대로 반환
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS embedding_targets (
  id            INT          NOT NULL AUTO_INCREMENT,
  target_key    VARCHAR(48)  NOT NULL UNIQUE
    COMMENT 'embeddings.target_type 에 들어가는 키',
  label         VARCHAR(128) NOT NULL,
  source_table  VARCHAR(64)  NOT NULL
    COMMENT '실제 텍스트가 들어있는 테이블 이름',
  source_field  VARCHAR(64)  NULL
    COMMENT '텍스트 컬럼 이름 또는 file_path 컬럼 이름',
  description   VARCHAR(512) NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO embedding_targets
    (target_key, label, source_table, source_field, description)
VALUES
  ('requirement',    '요구사항',
     'requirements',   'summary',
     '정제된 요구사항(요약/체크리스트) 텍스트'),
  ('user_code',      '사용자 입력 코드',
     'raw_inputs',     'raw_text',
     '사용자가 직접 입력/업로드한 원본 코드 (raw_inputs.raw_text)'),
  ('image_text',     '이미지 추출 텍스트',
     'image_data',     'text_file_path',
     '이미지에서 OCR/파싱한 자연어 텍스트'),
  ('image_code',     '이미지 추출 코드',
     'extracted_code', 'code_text',
     '이미지에서 추출한 코드 스니펫'),
  ('model_answer',   '모델 답변',
     'model_answers',  'answer_text',
     'LLM 이 생성한 답변 본문'),
  ('optimized_code', '최적화 코드',
     'optimized_code', 'code_text',
     '최적화/리팩터된 코드'),
  ('spec_structure', '명세서 구조',
     'image_data',     'spec_file_path',
     '이미지에서 추출한 명세서/스펙 구조 텍스트')
ON DUPLICATE KEY UPDATE
  label        = VALUES(label),
  source_table = VALUES(source_table),
  source_field = VALUES(source_field),
  description  = VALUES(description);

-- -----------------------------------------------------
-- 2) embeddings : 사진 명세 컬럼 호환 (model_version 등)
--    - 기존 컬럼(model_name/dim/vector_json)은 유지
--    - model_version 은 model_name 의 별칭으로 사용
-- -----------------------------------------------------
ALTER TABLE embeddings
  ADD COLUMN IF NOT EXISTS model_version VARCHAR(64) NULL
    COMMENT '사진 명세 호환: 임베딩 모델 버전 (없으면 model_name 사용)',
  ADD COLUMN IF NOT EXISTS source_text_hash CHAR(64) NULL
    COMMENT '원문 sha256 (content_hash 와 동일, 명시적 alias)',
  ADD KEY IF NOT EXISTS idx_emb_target_pair (target_type, target_id),
  ADD KEY IF NOT EXISTS idx_emb_search_model_dim_type (model_name, dim, target_type),
  ADD KEY IF NOT EXISTS idx_emb_search_version_dim_type (model_version, dim, target_type),
  ADD KEY IF NOT EXISTS idx_emb_created (created_at);

-- -----------------------------------------------------
-- 3) embeddings_view : 사진의 컬럼명 그대로 노출
--    - embedding_id / target_type / target_id /
--      model_version / vector_dim / vector_data / created_at
-- -----------------------------------------------------
CREATE OR REPLACE VIEW embeddings_view AS
SELECT
  e.id                                    AS embedding_id,
  e.target_type                           AS target_type,
  e.target_id                             AS target_id,
  COALESCE(e.model_version, e.model_name) AS model_version,
  e.dim                                   AS vector_dim,
  e.vector_json                           AS vector_data,
  e.norm                                  AS vector_norm,
  e.content_hash                          AS content_hash,
  e.vector_file_path                      AS vector_file_path,
  e.created_at                            AS created_at
FROM embeddings e;

-- -----------------------------------------------------
-- 4) answer_reuse_logs : 유사도 검색 메타 추가
--    - "유사도 검색 → 관련 답변 재사용" 흐름 감사용
-- -----------------------------------------------------
ALTER TABLE answer_reuse_logs
  ADD COLUMN IF NOT EXISTS query_target_type VARCHAR(48) NULL
    COMMENT '검색 입력으로 사용한 대상 타입 (raw_input/requirement 등)',
  ADD COLUMN IF NOT EXISTS query_text_hash   CHAR(64)    NULL
    COMMENT '검색 입력 텍스트의 sha256 (재현/감사용)',
  ADD COLUMN IF NOT EXISTS top_k             INT UNSIGNED NULL,
  ADD COLUMN IF NOT EXISTS threshold         DECIMAL(6,5) NULL;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step13',
        'Step 13: embedding targets catalog + spec-named view + reuse log enrichment');
