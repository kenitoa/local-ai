-- =====================================================
-- local-ai Step 19 마이그레이션
--   목적: "테스트 / 벤치마크" - 사진 19단계 체크리스트의
--         시스템 / AI 기능 / 성능 테스트를 영구 기록한다.
--
--   사진 체크리스트:
--     [시스템 테스트]
--       Windows 10, Windows 11, Docker 설치됨, Docker 미설치,
--       GPU 있음, GPU 없음, RAM 부족, 저장공간 부족
--     [AI 기능 테스트]
--       코드 입력, 코드 이미지 입력, 에러 이미지 입력, 명세서 이미지 입력,
--       답변 저장, embedding 저장, 과거 답변 재사용, 여러 언어 입력
--     [성능 테스트]
--       CPU 모드 속도, GPU 모드 속도, 이미지 처리 속도,
--       답변 생성 속도, MySQL 검색 속도, embedding 유사도 검색 속도
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) benchmark_runs : 벤치마크 실행 1회당 1행
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_runs (
  id              INT           NOT NULL AUTO_INCREMENT,
  triggered_by    VARCHAR(64)   NULL  COMMENT 'web-ui / cli / launcher 등',
  host_name       VARCHAR(255)  NULL,
  os_name         VARCHAR(64)   NULL,
  os_version      VARCHAR(64)   NULL,
  run_mode        ENUM('cpu','gpu','unknown')
                                NOT NULL DEFAULT 'unknown',
  accelerator     VARCHAR(64)   NULL  COMMENT 'cuda / directml / cpu / mps',
  total_items     INT UNSIGNED  NOT NULL DEFAULT 0,
  passed_items    INT UNSIGNED  NOT NULL DEFAULT 0,
  failed_items    INT UNSIGNED  NOT NULL DEFAULT 0,
  skipped_items   INT UNSIGNED  NOT NULL DEFAULT 0,
  info_items      INT UNSIGNED  NOT NULL DEFAULT 0,
  total_latency_ms INT UNSIGNED NULL,
  status          ENUM('running','passed','failed','partial')
                                NOT NULL DEFAULT 'running',
  notes           TEXT          NULL,
  started_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at     TIMESTAMP     NULL,
  PRIMARY KEY (id),
  KEY idx_bm_runs_status (status),
  KEY idx_bm_runs_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------
-- 2) benchmark_items : 체크리스트 한 항목당 1행
--    - 사진 체크리스트의 각 항목과 1:1
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_items (
  id            INT           NOT NULL AUTO_INCREMENT,
  run_id        INT           NOT NULL,
  category      ENUM('system','ai','perf') NOT NULL,
  item_no       INT UNSIGNED  NOT NULL,
  item_key      VARCHAR(64)   NOT NULL  COMMENT 'windows_10 / code_input / cpu_speed / ...',
  label         VARCHAR(255)  NOT NULL,
  status        ENUM('passed','failed','skipped','info','running')
                              NOT NULL DEFAULT 'running',
  value_ms      INT UNSIGNED  NULL  COMMENT '성능 측정 ms (해당 시)',
  value_text    VARCHAR(255)  NULL  COMMENT '값(예: RAM=12.0GB, OS=Windows 11 등)',
  message       TEXT          NULL,
  evidence_json JSON          NULL,
  created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_bm_items_run (run_id, item_no),
  KEY idx_bm_items_status (status),
  KEY idx_bm_items_cat (category),
  CONSTRAINT fk_bm_items_run
    FOREIGN KEY (run_id) REFERENCES benchmark_runs(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step19',
        'Step 19: test / benchmark checklist (system + AI + performance)');
