-- =====================================================
-- local-ai 마이그레이션: 자체 학습 예산(plan)
--   목적: hardware_profiles → model_planner.plan_all() 결과 영속화.
--         "어떤 외부 모델을 받을까" 가 아니라
--         "이 기기에서 *내가 만든 모델을* 어떻게 학습/추론할까" 를 기록한다.
--
--   schema_version
--     1 = (폐기) 외부 모델 선택형
--     2 = 자체 학습형(A안). 콜드스타트 베이스 1회만 외부 다운로드 허용,
--         이후 모든 학습은 자체 fine-tune.
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE IF NOT EXISTS model_plans (
  id                   INT           NOT NULL AUTO_INCREMENT,
  hardware_profile_id  INT           NULL,
  fingerprint          CHAR(64)      NOT NULL
    COMMENT 'hardware_profiles.fingerprint 와 동일 (인덱싱용 사본)',
  schema_version       SMALLINT      NOT NULL DEFAULT 2,

  -- 콜드스타트 베이스 (유일한 외부 다운로드)
  bootstrap_base_id        VARCHAR(128)  NOT NULL
    COMMENT '예: Qwen/Qwen2.5-Coder-1.5B. 1회만 다운로드.',
  bootstrap_params_b       DECIMAL(6,2)  NOT NULL,
  bootstrap_license        VARCHAR(64)   NULL,
  external_download_policy VARCHAR(32)   NOT NULL DEFAULT 'cold-start-only'
    COMMENT 'cold-start-only | none. 콜드스타트 외 외부 다운로드 금지.',

  -- 학습 예산
  train_trainable          TINYINT(1)    NOT NULL DEFAULT 0,
  train_method             VARCHAR(16)   NOT NULL
    COMMENT 'full | lora | qlora | disabled',
  train_device             VARCHAR(16)   NOT NULL,
  train_precision          VARCHAR(16)   NULL
    COMMENT 'fp32 | bf16 | fp16 | int8',
  train_lora_rank          INT           NOT NULL DEFAULT 0,
  train_lora_alpha         INT           NOT NULL DEFAULT 0,
  train_lora_dropout       DECIMAL(5,3)  NOT NULL DEFAULT 0.000,
  train_per_dev_batch      INT           NOT NULL DEFAULT 1,
  train_grad_accum_steps   INT           NOT NULL DEFAULT 1,
  train_effective_batch    INT           NOT NULL DEFAULT 1,
  train_seq_len            INT           NOT NULL DEFAULT 512,
  train_grad_checkpointing TINYINT(1)    NOT NULL DEFAULT 0,
  train_optimizer          VARCHAR(32)   NULL,
  train_n_threads          INT           NOT NULL DEFAULT 2,
  train_max_params_b       DECIMAL(6,2)  NOT NULL DEFAULT 1.50,
  train_disabled_reason    VARCHAR(255)  NULL,

  -- 추론 예산 (자체 가중치 추론용)
  infer_device             VARCHAR(16)   NOT NULL,
  infer_n_ctx              INT           NOT NULL,
  infer_n_batch            INT           NOT NULL,
  infer_n_threads          INT           NOT NULL,
  infer_n_gpu_layers       INT           NOT NULL DEFAULT 0,
  infer_max_concurrency    SMALLINT      NOT NULL DEFAULT 1,

  summary                  VARCHAR(512)  NULL,
  raw_json                 JSON          NULL,
  created_at               TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  KEY idx_model_plans_fingerprint (fingerprint),
  KEY idx_model_plans_hw          (hardware_profile_id),
  CONSTRAINT fk_model_plans_hw FOREIGN KEY (hardware_profile_id)
    REFERENCES hardware_profiles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-self-train-plan',
        'model_plans v2: 자체 학습형. 콜드스타트 1B 베이스 1회 + 자체 fine-tune.');
