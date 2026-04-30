-- =====================================================
-- local-ai Step 17 마이그레이션
--   목적: "전체 통합" - 사진 17단계 체크리스트의 시나리오를
--         한 번에 실행하고 각 단계별 통과/실패를 영구 기록한다.
--
--   사진 통합 테스트 시나리오:
--     [.exe 실행] [Docker Compose 자동 실행] [Web UI 자동 오픈]
--     [코드 입력] [모델 답변 생성] [답변 저장] [embedding 저장]
--     [같은 요구사항 재입력] [기존 답변 재사용]
--     [코드 이미지 업로드] [이미지에서 코드 추출] [추출 코드 기반 답변 생성]
--     [GPU 없을 때 CPU fallback 확인]
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- 1) integration_runs : 통합 테스트 실행 1회당 1행
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS integration_runs (
  id              INT           NOT NULL AUTO_INCREMENT,
  triggered_by    VARCHAR(64)   NULL  COMMENT 'web-ui / cli / launcher 등',
  host_name       VARCHAR(255)  NULL,
  run_mode        ENUM('cpu','gpu','unknown')
                                NOT NULL DEFAULT 'unknown',
  accelerator     VARCHAR(64)   NULL  COMMENT 'cuda / directml / cpu / mps',
  total_steps     INT UNSIGNED  NOT NULL DEFAULT 0,
  passed_steps    INT UNSIGNED  NOT NULL DEFAULT 0,
  failed_steps    INT UNSIGNED  NOT NULL DEFAULT 0,
  skipped_steps   INT UNSIGNED  NOT NULL DEFAULT 0,
  total_latency_ms INT UNSIGNED NULL,
  status          ENUM('running','passed','failed','partial')
                                NOT NULL DEFAULT 'running',
  notes           TEXT          NULL,
  started_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at     TIMESTAMP     NULL,
  PRIMARY KEY (id),
  KEY idx_int_runs_status (status),
  KEY idx_int_runs_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------
-- 2) integration_steps : 시나리오 단계별 결과
--    - 사진 체크리스트의 각 항목과 1:1 대응
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS integration_steps (
  id            INT           NOT NULL AUTO_INCREMENT,
  run_id        INT           NOT NULL,
  step_no       INT UNSIGNED  NOT NULL,
  step_key      VARCHAR(64)   NOT NULL  COMMENT 'launcher_exe / compose_up / ...',
  label         VARCHAR(255)  NOT NULL,
  category      VARCHAR(32)   NULL      COMMENT 'environment / pipeline / reuse / vision / hardware',
  status        ENUM('passed','failed','skipped','running')
                              NOT NULL DEFAULT 'running',
  latency_ms    INT UNSIGNED  NULL,
  message       TEXT          NULL,
  evidence_json JSON          NULL      COMMENT '단계 산출물 (answer_id, image_id 등)',
  created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_int_steps_run (run_id, step_no),
  KEY idx_int_steps_status (status),
  CONSTRAINT fk_int_steps_run
    FOREIGN KEY (run_id) REFERENCES integration_runs(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step17',
        'Step 17: full integration test scenarios + per-step run log');
