-- =====================================================
-- local-ai Step 15 마이그레이션
--   목적: "코드 최적화 엔진" - LLM만으로 최적화하지 말고
--          규칙 기반 정적 분석도 같이 두는 하이브리드 파이프라인.
--
--   사진 명세 흐름:
--     코드 입력 → 언어 감지 → 정적 분석 → 라이브러리 패턴 검색
--       → 과거 답변 검색 → LLM 최적화 → 결과 비교 → 저장
--
--   사진 명세 최적화 유형(9가지):
--     문법 오류 수정, 오탈자 수정, 불필요한 코드 제거,
--     반복문 개선, 메모리 사용량 개선, 라이브러리 대체,
--     알고리즘 개선, 가독성 개선, 실행 속도 개선
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) optimization_types : 사진의 9가지 최적화 유형 카탈로그
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS optimization_types (
  id          INT          NOT NULL AUTO_INCREMENT,
  type_key    VARCHAR(48)  NOT NULL UNIQUE
    COMMENT '코드: syntax_error, typo, dead_code, loop, memory, library, algorithm, readability, speed',
  label       VARCHAR(128) NOT NULL,
  description VARCHAR(512) NULL,
  sort_order  INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO optimization_types (type_key, label, description, sort_order) VALUES
  ('syntax_error', '문법 오류 수정',     '컴파일/해석 단계에서 실패하는 구문 오류 수정',                  1),
  ('typo',         '오탈자 수정',        '식별자/표준 라이브러리 이름의 흔한 오탈자 교정',                2),
  ('dead_code',    '불필요한 코드 제거', '미사용 import / 변수 / 도달 불가능 코드 제거',                  3),
  ('loop',         '반복문 개선',        'range(len(x)) → enumerate, 중첩 루프 단순화 등',                4),
  ('memory',       '메모리 사용량 개선', '리스트→제너레이터, 한 번에 read() → 스트림 처리 등',           5),
  ('library',      '라이브러리 대체',    '내장/표준/더 빠른 라이브러리로 교체 (예: json, httpx, polars)', 6),
  ('algorithm',    '알고리즘 개선',      'O(n^2) → O(n log n)/해시 사용 등 복잡도 개선',                  7),
  ('readability',  '가독성 개선',        '긴 라인/매직 넘버/깊은 들여쓰기 정리 + 네이밍',                 8),
  ('speed',        '실행 속도 개선',     '문자열 누적, 중복 호출, 캐싱 가능한 호출 등 핫스팟 정리',       9)
ON DUPLICATE KEY UPDATE
  label       = VALUES(label),
  description = VALUES(description),
  sort_order  = VALUES(sort_order);

-- -----------------------------------------------------
-- 2) optimization_runs : 코드 최적화 엔진 실행 이력
--    - 사진의 8단계(언어 감지 → ... → 저장) 산출물을 한 행에 보존
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS optimization_runs (
  id                   INT           NOT NULL AUTO_INCREMENT,
  raw_input_id         INT           NULL,
  generated_code_id    INT           NULL
    COMMENT '엔진이 자동 생성한 generated_code 행 (있을 경우)',
  optimized_code_id    INT           NULL
    COMMENT '엔진이 저장한 optimized_code 행',
  language             VARCHAR(48)   NULL,
  language_source      VARCHAR(32)   NULL  COMMENT 'hint / language-worker / fallback',
  input_code           MEDIUMTEXT    NULL,
  output_code          MEDIUMTEXT    NULL,
  diff_text            MEDIUMTEXT    NULL,
  static_analysis_json JSON          NULL  COMMENT '규칙 기반 분석 결과 (findings 요약)',
  library_matches_json JSON          NULL  COMMENT '검색된 라이브러리 패턴 후보',
  similar_answers_json JSON          NULL  COMMENT '재사용 가능한 과거 답변 후보',
  comparison_json      JSON          NULL  COMMENT '결과 비교: 라인 변화/적용된 유형/규칙 vs LLM 비중',
  llm_model            VARCHAR(255)  NULL,
  llm_latency_ms       INT UNSIGNED  NULL,
  total_latency_ms     INT UNSIGNED  NULL,
  rule_only            TINYINT(1)    NOT NULL DEFAULT 0
    COMMENT 'LLM 호출 없이 규칙 기반 결과만 사용한 경우 1',
  status               ENUM('ok','partial','failed') NOT NULL DEFAULT 'ok',
  notes                VARCHAR(512)  NULL,
  created_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_optrun_raw       (raw_input_id),
  KEY idx_optrun_generated (generated_code_id),
  KEY idx_optrun_optimized (optimized_code_id),
  KEY idx_optrun_created   (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 3) optimization_findings : 단일 finding (규칙/LLM/라이브러리)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS optimization_findings (
  id          INT          NOT NULL AUTO_INCREMENT,
  run_id      INT          NOT NULL,
  type_key    VARCHAR(48)  NOT NULL
    COMMENT 'optimization_types.type_key',
  source      ENUM('rule','llm','library','reuse') NOT NULL DEFAULT 'rule',
  severity    ENUM('info','warn','error') NOT NULL DEFAULT 'info',
  line_no     INT          NULL,
  col_no      INT          NULL,
  rule_id     VARCHAR(64)  NULL  COMMENT '규칙 식별자 (예: PY001 unused-import)',
  message     VARCHAR(512) NOT NULL,
  suggestion  MEDIUMTEXT   NULL,
  snippet     TEXT         NULL,
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_finding_run       (run_id),
  KEY idx_finding_type      (type_key),
  CONSTRAINT fk_finding_run
    FOREIGN KEY (run_id) REFERENCES optimization_runs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step15',
        'Step 15: code optimization engine (rule-based + library + reuse + LLM)');
