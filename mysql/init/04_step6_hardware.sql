-- =====================================================
-- local-ai Step 6 마이그레이션
--   목적: 하드웨어 감지 결과(실행 모드/저장공간/가속기 가용성) 컬럼 추가
--   - hardware-detector 서비스가 채움
--   - 기존 hardware_profiles 테이블을 확장
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

ALTER TABLE hardware_profiles
  ADD COLUMN IF NOT EXISTS run_mode           VARCHAR(16)   NULL
    COMMENT 'gpu | cpu (실행 모드 결정 결과)',
  ADD COLUMN IF NOT EXISTS gpu_present        TINYINT(1)    NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gpu_vendor         VARCHAR(64)   NULL
    COMMENT 'nvidia | amd | intel | apple | unknown',
  ADD COLUMN IF NOT EXISTS cuda_available     TINYINT(1)    NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS directml_available TINYINT(1)    NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS docker_gpu_ok      TINYINT(1)    NOT NULL DEFAULT 0
    COMMENT '컨테이너 내부에서 GPU 접근 가능 여부',
  ADD COLUMN IF NOT EXISTS storage_total_gb   DECIMAL(10,2) NULL,
  ADD COLUMN IF NOT EXISTS storage_free_gb    DECIMAL(10,2) NULL,
  ADD COLUMN IF NOT EXISTS detected_at        TIMESTAMP     NULL
    COMMENT '마지막 감지 시각';

CREATE INDEX IF NOT EXISTS idx_hw_run_mode    ON hardware_profiles (run_mode);
CREATE INDEX IF NOT EXISTS idx_hw_detected_at ON hardware_profiles (detected_at);

INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step6', 'Step 6: hardware detector fields (run_mode/gpu/storage)');
