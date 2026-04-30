-- =====================================================
-- local-ai Step 14 마이그레이션
--   목적: "답변 재사용 구조" - 모델은 매번 새로 답하지 않고
--          기존 답변을 검색·재사용하고 필요한 부분만 수정한다.
--
--   사진 명세 흐름:
--     새 요구사항 입력 → embedding 생성 → MySQL에서 유사 답변 검색
--       → 유사도 기준 이상이면 기존 답변 후보 반환
--       → LLM이 기존 답변을 현재 요구사항에 맞게 수정
--       → 새 답변 저장
--
--   체크리스트:
--     - 유사 요구사항/코드/이미지 추출/답변 검색
--     - reuse_count 증가
--     - 재사용 로그 저장
--     - 수정된 답변은 새 답변으로 저장
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) model_answers.reuse_count
--    - 같은 답변이 재사용된 횟수 (재사용 시마다 +1)
--    - 사진 체크리스트의 "reuse_count 증가" 항목 충족
-- -----------------------------------------------------
ALTER TABLE model_answers
  ADD COLUMN IF NOT EXISTS reuse_count INT UNSIGNED NOT NULL DEFAULT 0
    COMMENT '이 답변이 재사용된 누적 횟수 (Step 14)',
  ADD COLUMN IF NOT EXISTS last_reused_at TIMESTAMP NULL
    COMMENT '가장 최근 재사용 시각 (Step 14)',
  ADD KEY IF NOT EXISTS idx_ma_reuse_count (reuse_count);

-- -----------------------------------------------------
-- 2) answer_reuse_logs : 재사용 감사 로그 강화
--    - 후보들 JSON, 어떤 단계까지 진행됐는지(adapted/saved) 기록
-- -----------------------------------------------------
ALTER TABLE answer_reuse_logs
  ADD COLUMN IF NOT EXISTS candidates_json JSON NULL
    COMMENT '검색된 상위 후보 목록 (target_type/target_id/similarity)',
  ADD COLUMN IF NOT EXISTS adapted TINYINT(1) NOT NULL DEFAULT 0
    COMMENT 'LLM 이 기존 답변을 현재 요구사항에 맞게 수정했는지',
  ADD COLUMN IF NOT EXISTS adaptation_prompt MEDIUMTEXT NULL
    COMMENT 'LLM 적응(adapt) 단계에서 사용한 프롬프트',
  ADD COLUMN IF NOT EXISTS adaptation_model VARCHAR(255) NULL
    COMMENT 'adapt 단계에서 사용한 LLM 모델명',
  ADD COLUMN IF NOT EXISTS latency_ms INT UNSIGNED NULL
    COMMENT '재사용 파이프라인 전체 소요시간 (ms)';

-- -----------------------------------------------------
-- 3) 단순 통계용 view (재사용 핫 답변 상위)
-- -----------------------------------------------------
CREATE OR REPLACE VIEW model_answer_reuse_stats AS
SELECT
  ma.id                  AS answer_id,
  ma.model_name          AS model_name,
  ma.reuse_count         AS reuse_count,
  ma.last_reused_at      AS last_reused_at,
  ma.created_at          AS created_at,
  LEFT(ma.answer_text, 240) AS answer_preview
FROM model_answers ma
WHERE ma.reuse_count > 0;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step14',
        'Step 14: answer reuse loop (reuse_count + reuse logs + adapted answers)');
