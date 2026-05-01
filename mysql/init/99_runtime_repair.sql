USE localai_db;

DELIMITER //

CREATE PROCEDURE add_col_if_missing(
  IN p_table VARCHAR(64),
  IN p_col VARCHAR(64),
  IN p_def TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = p_table
       AND column_name = p_col
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN `', p_col, '` ', p_def);
    PREPARE stmt FROM @ddl;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END//

DELIMITER ;

CALL add_col_if_missing('raw_inputs', 'source_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('raw_inputs', 'detected_language', 'VARCHAR(64) NULL');
CALL add_col_if_missing('raw_inputs', 'support_level', 'TINYINT UNSIGNED NULL');

CALL add_col_if_missing('image_data', 'text_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('image_data', 'code_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('image_data', 'spec_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('image_data', 'metadata_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('image_data', 'image_type', 'VARCHAR(32) NULL');
CALL add_col_if_missing('image_data', 'image_type_source', 'VARCHAR(16) NULL');
CALL add_col_if_missing('image_data', 'image_type_confidence', 'DECIMAL(5,4) NULL');
CALL add_col_if_missing('image_data', 'extraction_status', 'VARCHAR(16) NULL DEFAULT ''pending''');
CALL add_col_if_missing('image_data', 'extraction_engine', 'VARCHAR(64) NULL');
CALL add_col_if_missing('image_data', 'extracted_at', 'TIMESTAMP NULL');

CALL add_col_if_missing('extracted_code', 'file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('extracted_code', 'file_size', 'INT UNSIGNED NULL');
CALL add_col_if_missing('extracted_code', 'sha256', 'CHAR(64) NULL');

CALL add_col_if_missing('model_answers', 'answer_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('model_answers', 'file_size', 'INT UNSIGNED NULL');
CALL add_col_if_missing('model_answers', 'sha256', 'CHAR(64) NULL');
CALL add_col_if_missing('model_answers', 'reuse_count', 'INT UNSIGNED NOT NULL DEFAULT 0');
CALL add_col_if_missing('model_answers', 'last_reused_at', 'TIMESTAMP NULL');

CALL add_col_if_missing('generated_code', 'file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('generated_code', 'file_size', 'INT UNSIGNED NULL');
CALL add_col_if_missing('generated_code', 'sha256', 'CHAR(64) NULL');

CALL add_col_if_missing('optimized_code', 'file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('optimized_code', 'diff_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('optimized_code', 'file_size', 'INT UNSIGNED NULL');
CALL add_col_if_missing('optimized_code', 'sha256', 'CHAR(64) NULL');

ALTER TABLE embeddings MODIFY COLUMN vector_json JSON NULL;
CALL add_col_if_missing('embeddings', 'vector_file_path', 'VARCHAR(1024) NULL');
CALL add_col_if_missing('embeddings', 'file_size', 'INT UNSIGNED NULL');
CALL add_col_if_missing('embeddings', 'sha256', 'CHAR(64) NULL');
CALL add_col_if_missing('embeddings', 'model_version', 'VARCHAR(64) NULL');
CALL add_col_if_missing('embeddings', 'source_text_hash', 'CHAR(64) NULL');
CREATE INDEX IF NOT EXISTS idx_emb_search_model_dim_type ON embeddings (model_name, dim, target_type);
CREATE INDEX IF NOT EXISTS idx_emb_search_version_dim_type ON embeddings (model_version, dim, target_type);

CALL add_col_if_missing('answer_reuse_logs', 'query_target_type', 'VARCHAR(48) NULL');
CALL add_col_if_missing('answer_reuse_logs', 'query_text_hash', 'CHAR(64) NULL');
CALL add_col_if_missing('answer_reuse_logs', 'top_k', 'INT UNSIGNED NULL');
CALL add_col_if_missing('answer_reuse_logs', 'threshold', 'DECIMAL(6,5) NULL');
CALL add_col_if_missing('answer_reuse_logs', 'candidates_json', 'JSON NULL');
CALL add_col_if_missing('answer_reuse_logs', 'adapted', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_col_if_missing('answer_reuse_logs', 'adaptation_prompt', 'MEDIUMTEXT NULL');
CALL add_col_if_missing('answer_reuse_logs', 'adaptation_model', 'VARCHAR(255) NULL');
CALL add_col_if_missing('answer_reuse_logs', 'latency_ms', 'INT UNSIGNED NULL');

CALL add_col_if_missing('hardware_profiles', 'run_mode', 'VARCHAR(16) NULL');
CALL add_col_if_missing('hardware_profiles', 'gpu_present', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_col_if_missing('hardware_profiles', 'gpu_vendor', 'VARCHAR(64) NULL');
CALL add_col_if_missing('hardware_profiles', 'cuda_available', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_col_if_missing('hardware_profiles', 'directml_available', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_col_if_missing('hardware_profiles', 'docker_gpu_ok', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_col_if_missing('hardware_profiles', 'storage_total_gb', 'DECIMAL(10,2) NULL');
CALL add_col_if_missing('hardware_profiles', 'storage_free_gb', 'DECIMAL(10,2) NULL');
CALL add_col_if_missing('hardware_profiles', 'detected_at', 'VARCHAR(64) NULL');

CREATE TABLE IF NOT EXISTS embedding_targets (
  id INT NOT NULL AUTO_INCREMENT,
  target_key VARCHAR(48) NOT NULL UNIQUE,
  label VARCHAR(128) NOT NULL,
  source_table VARCHAR(64) NOT NULL,
  source_field VARCHAR(64) NULL,
  description VARCHAR(512) NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO embedding_targets (target_key, label, source_table, source_field, description) VALUES
  ('requirement','Requirement','requirements','summary','Requirement text'),
  ('user_code','User code','raw_inputs','raw_text','User-provided code'),
  ('image_text','Image text','image_data','text_file_path','Extracted image text'),
  ('image_code','Image code','extracted_code','code_text','Extracted image code'),
  ('model_answer','Model answer','model_answers','answer_text','Saved answer'),
  ('optimized_code','Optimized code','optimized_code','code_text','Optimized code'),
  ('spec_structure','Spec structure','image_data','spec_file_path','Extracted spec structure')
ON DUPLICATE KEY UPDATE
  label=VALUES(label), source_table=VALUES(source_table),
  source_field=VALUES(source_field), description=VALUES(description);

CREATE TABLE IF NOT EXISTS llm_training_stages (
  id INT NOT NULL AUTO_INCREMENT,
  stage_no INT NOT NULL UNIQUE,
  stage_key VARCHAR(48) NOT NULL UNIQUE,
  label VARCHAR(128) NOT NULL,
  description VARCHAR(512) NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO llm_training_stages (stage_no, stage_key, label, description) VALUES
  (1,'tokenizer_design','Tokenizer design','Tokenizer configuration'),
  (2,'data_format_design','Data format design','Dataset schema'),
  (3,'collect_code_corpus','Collect code corpus','Raw code corpus'),
  (4,'curate_library_docs','Curate library docs','Library examples'),
  (5,'build_optimize_pairs','Build optimize pairs','Input/output optimize pairs'),
  (6,'build_spec_to_code','Build spec-to-code','Requirement to code samples'),
  (7,'build_code_to_explain','Build code-to-explain','Code explanation samples'),
  (8,'pretrain','Pretrain','Language model pretraining'),
  (9,'instruction_tuning','Instruction tuning','SFT instruction tuning'),
  (10,'finetune_optimize','Fine-tune optimize','Optimization fine-tuning'),
  (11,'evaluate','Evaluate','Evaluation'),
  (12,'serve_inference','Serve inference','Inference server')
ON DUPLICATE KEY UPDATE label=VALUES(label), description=VALUES(description);

CREATE TABLE IF NOT EXISTS llm_tokenizer_configs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL UNIQUE,
  algorithm VARCHAR(32) NOT NULL DEFAULT 'bpe',
  vocab_size INT NOT NULL DEFAULT 32000,
  special_tokens JSON NULL,
  notes TEXT NULL,
  config_file_path VARCHAR(512) NULL,
  artifact_file_path VARCHAR(512) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_code_corpus (
  id BIGINT NOT NULL AUTO_INCREMENT,
  language VARCHAR(32) NOT NULL,
  source VARCHAR(64) NULL,
  source_url VARCHAR(1024) NULL,
  file_name VARCHAR(255) NULL,
  file_path VARCHAR(512) NOT NULL,
  file_size INT UNSIGNED NULL,
  sha256 CHAR(64) NULL,
  license VARCHAR(64) NULL,
  token_count INT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'collected',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_corpus_lang (language)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_library_examples (
  id BIGINT NOT NULL AUTO_INCREMENT,
  language VARCHAR(32) NOT NULL,
  library VARCHAR(128) NOT NULL,
  version VARCHAR(32) NULL,
  topic VARCHAR(255) NULL,
  doc_text MEDIUMTEXT NULL,
  example_code MEDIUMTEXT NULL,
  source_url VARCHAR(1024) NULL,
  file_path VARCHAR(512) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'curated',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_lib_lang_lib (language, library)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_training_samples (
  id BIGINT NOT NULL AUTO_INCREMENT,
  stage_id INT NULL,
  task VARCHAR(32) NOT NULL,
  language VARCHAR(32) NOT NULL,
  library VARCHAR(128) NULL,
  input_code MEDIUMTEXT NULL,
  requirement MEDIUMTEXT NULL,
  output_code MEDIUMTEXT NULL,
  explanation MEDIUMTEXT NULL,
  meta_json JSON NULL,
  sample_file_path VARCHAR(512) NULL,
  split VARCHAR(16) NOT NULL DEFAULT 'train',
  source VARCHAR(32) NOT NULL DEFAULT 'manual',
  quality_score DECIMAL(5,4) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ready',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_sample_task (task),
  KEY idx_llm_sample_lang (language)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_training_runs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  stage_id INT NOT NULL,
  stage_key VARCHAR(48) NOT NULL,
  run_name VARCHAR(128) NULL,
  base_model VARCHAR(128) NULL,
  tokenizer_id BIGINT NULL,
  dataset_filter JSON NULL,
  hyperparams JSON NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  metrics_json JSON NULL,
  log_file_path VARCHAR(512) NULL,
  checkpoint_path VARCHAR(512) NULL,
  started_at TIMESTAMP NULL,
  finished_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_run_stage (stage_id),
  KEY idx_llm_run_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_eval_results (
  id BIGINT NOT NULL AUTO_INCREMENT,
  training_run_id BIGINT NULL,
  task VARCHAR(32) NOT NULL,
  metric_name VARCHAR(64) NOT NULL,
  metric_value DECIMAL(10,6) NOT NULL,
  sample_count INT NULL,
  detail_json JSON NULL,
  report_file_path VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_inference_runs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  endpoint VARCHAR(32) NOT NULL,
  model_name VARCHAR(128) NULL,
  language VARCHAR(32) NULL,
  library VARCHAR(128) NULL,
  input_code MEDIUMTEXT NULL,
  requirement MEDIUMTEXT NULL,
  output_code MEDIUMTEXT NULL,
  explanation MEDIUMTEXT NULL,
  raw_response JSON NULL,
  latency_ms INT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ok',
  answer_id BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_llm_inf_endpoint (endpoint)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vlm_training_stages (
  id INT NOT NULL AUTO_INCREMENT,
  stage_no INT NOT NULL UNIQUE,
  stage_key VARCHAR(32) NOT NULL UNIQUE,
  label VARCHAR(128) NOT NULL,
  image_type VARCHAR(32) NOT NULL,
  description VARCHAR(255) NULL,
  is_initial TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO vlm_training_stages (stage_no, stage_key, label, image_type, description, is_initial) VALUES
  (1,'code_image','Code image recognition','code','Extract code from screenshots',1),
  (2,'error_log_image','Error log recognition','error_log','Extract error logs',0),
  (3,'spec_image','Spec image recognition','tech_spec','Extract technical specs',0),
  (4,'table_structure','Table structure recognition','db_design','Extract database design',0),
  (5,'ui_layout','UI layout recognition','ui_design','Extract UI layout',0)
ON DUPLICATE KEY UPDATE label=VALUES(label), image_type=VALUES(image_type), description=VALUES(description);

CREATE TABLE IF NOT EXISTS vlm_training_samples (
  id BIGINT NOT NULL AUTO_INCREMENT,
  stage_id INT NOT NULL,
  stage_key VARCHAR(32) NOT NULL,
  image_type VARCHAR(32) NOT NULL,
  image_id BIGINT NULL,
  image_path VARCHAR(512) NOT NULL,
  expected_text MEDIUMTEXT NULL,
  expected_code MEDIUMTEXT NULL,
  expected_language VARCHAR(32) NULL,
  expected_structure JSON NULL,
  sample_file_path VARCHAR(512) NULL,
  split VARCHAR(16) NOT NULL DEFAULT 'train',
  source VARCHAR(32) NOT NULL DEFAULT 'manual',
  user_tag VARCHAR(64) NULL,
  notes VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vlm_pipeline_runs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  image_id BIGINT NULL,
  raw_input_id BIGINT NULL,
  pipeline VARCHAR(48) NOT NULL DEFAULT 'code_region_extract',
  detector VARCHAR(64) NULL,
  ocr_engine VARCHAR(64) NULL,
  region_count INT NULL,
  detected_regions JSON NULL,
  extracted_text MEDIUMTEXT NULL,
  text_file_path VARCHAR(512) NULL,
  llm_answer_id BIGINT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'done',
  latency_ms INT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS optimization_types (
  id INT NOT NULL AUTO_INCREMENT,
  type_key VARCHAR(48) NOT NULL UNIQUE,
  label VARCHAR(128) NOT NULL,
  description VARCHAR(512) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO optimization_types (type_key, label, description, sort_order) VALUES
  ('syntax_error','Syntax error','Fix syntax errors',1),
  ('typo','Typo','Fix typos',2),
  ('dead_code','Dead code','Remove dead code',3),
  ('loop','Loop improvement','Improve loops',4),
  ('memory','Memory improvement','Improve memory use',5),
  ('library','Library replacement','Use better libraries',6),
  ('algorithm','Algorithm improvement','Improve complexity',7),
  ('readability','Readability','Improve readability',8),
  ('speed','Speed','Improve execution speed',9)
ON DUPLICATE KEY UPDATE label=VALUES(label), description=VALUES(description), sort_order=VALUES(sort_order);

CREATE TABLE IF NOT EXISTS optimization_runs (
  id INT NOT NULL AUTO_INCREMENT,
  raw_input_id BIGINT NULL,
  generated_code_id BIGINT NULL,
  optimized_code_id BIGINT NULL,
  language VARCHAR(48) NULL,
  language_source VARCHAR(32) NULL,
  input_code MEDIUMTEXT NULL,
  output_code MEDIUMTEXT NULL,
  diff_text MEDIUMTEXT NULL,
  static_analysis_json JSON NULL,
  library_matches_json JSON NULL,
  similar_answers_json JSON NULL,
  comparison_json JSON NULL,
  llm_model VARCHAR(255) NULL,
  llm_latency_ms INT UNSIGNED NULL,
  total_latency_ms INT UNSIGNED NULL,
  rule_only TINYINT(1) NOT NULL DEFAULT 0,
  status ENUM('ok','partial','failed') NOT NULL DEFAULT 'ok',
  notes VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS optimization_findings (
  id INT NOT NULL AUTO_INCREMENT,
  run_id INT NOT NULL,
  type_key VARCHAR(48) NOT NULL,
  source ENUM('rule','llm','library','reuse') NOT NULL DEFAULT 'rule',
  severity ENUM('info','warn','error') NOT NULL DEFAULT 'info',
  line_no INT NULL,
  col_no INT NULL,
  rule_id VARCHAR(64) NULL,
  message VARCHAR(512) NOT NULL,
  suggestion MEDIUMTEXT NULL,
  snippet TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_finding_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spec_engine_runs (
  id INT NOT NULL AUTO_INCREMENT,
  raw_input_id BIGINT NULL,
  project_id BIGINT NULL,
  source_kind ENUM('text','image','file','mixed') NOT NULL DEFAULT 'text',
  source_image_id BIGINT NULL,
  spec_text MEDIUMTEXT NULL,
  spec_file_path VARCHAR(1024) NULL,
  project_name VARCHAR(255) NULL,
  target_language VARCHAR(48) NULL,
  target_framework VARCHAR(64) NULL,
  requirements_json JSON NULL,
  intermediate_json JSON NULL,
  features_json JSON NULL,
  screens_json JSON NULL,
  apis_json JSON NULL,
  database_tables_json JSON NULL,
  business_rules_json JSON NULL,
  project_structure_json JSON NULL,
  intermediate_file_path VARCHAR(1024) NULL,
  llm_model VARCHAR(255) NULL,
  llm_latency_ms INT UNSIGNED NULL,
  total_latency_ms INT UNSIGNED NULL,
  feature_count INT UNSIGNED NOT NULL DEFAULT 0,
  screen_count INT UNSIGNED NOT NULL DEFAULT 0,
  api_count INT UNSIGNED NOT NULL DEFAULT 0,
  table_count INT UNSIGNED NOT NULL DEFAULT 0,
  rule_count INT UNSIGNED NOT NULL DEFAULT 0,
  file_count INT UNSIGNED NOT NULL DEFAULT 0,
  status ENUM('ok','partial','failed') NOT NULL DEFAULT 'ok',
  notes VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spec_engine_files (
  id INT NOT NULL AUTO_INCREMENT,
  run_id INT NOT NULL,
  rel_path VARCHAR(512) NOT NULL,
  language VARCHAR(48) NULL,
  role ENUM('backend','frontend','db','config','docs','test','other') NOT NULL DEFAULT 'other',
  code_text MEDIUMTEXT NULL,
  file_path VARCHAR(1024) NULL,
  file_size INT UNSIGNED NULL,
  sha256 CHAR(64) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spec_engine_steps (
  id INT NOT NULL AUTO_INCREMENT,
  run_id INT NOT NULL,
  step_no TINYINT UNSIGNED NOT NULL,
  step_key VARCHAR(48) NOT NULL,
  label VARCHAR(128) NOT NULL,
  output_json JSON NULL,
  source ENUM('llm','rule','reuse','user') NOT NULL DEFAULT 'rule',
  llm_model VARCHAR(255) NULL,
  latency_ms INT UNSIGNED NULL,
  status ENUM('ok','partial','failed') NOT NULL DEFAULT 'ok',
  notes VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS integration_runs (
  id INT NOT NULL AUTO_INCREMENT,
  triggered_by VARCHAR(64) NULL,
  host_name VARCHAR(255) NULL,
  run_mode ENUM('cpu','gpu','unknown') NOT NULL DEFAULT 'unknown',
  accelerator VARCHAR(64) NULL,
  total_steps INT UNSIGNED NOT NULL DEFAULT 0,
  passed_steps INT UNSIGNED NOT NULL DEFAULT 0,
  failed_steps INT UNSIGNED NOT NULL DEFAULT 0,
  skipped_steps INT UNSIGNED NOT NULL DEFAULT 0,
  total_latency_ms INT UNSIGNED NULL,
  status ENUM('running','passed','failed','partial') NOT NULL DEFAULT 'running',
  notes TEXT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS integration_steps (
  id INT NOT NULL AUTO_INCREMENT,
  run_id INT NOT NULL,
  step_no INT UNSIGNED NOT NULL,
  step_key VARCHAR(64) NOT NULL,
  label VARCHAR(255) NOT NULL,
  category VARCHAR(32) NULL,
  status ENUM('passed','failed','skipped','running') NOT NULL DEFAULT 'running',
  latency_ms INT UNSIGNED NULL,
  message TEXT NULL,
  evidence_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_int_steps_run (run_id, step_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS benchmark_runs (
  id INT NOT NULL AUTO_INCREMENT,
  triggered_by VARCHAR(64) NULL,
  host_name VARCHAR(255) NULL,
  os_name VARCHAR(64) NULL,
  os_version VARCHAR(64) NULL,
  run_mode ENUM('cpu','gpu','unknown') NOT NULL DEFAULT 'unknown',
  accelerator VARCHAR(64) NULL,
  total_items INT UNSIGNED NOT NULL DEFAULT 0,
  passed_items INT UNSIGNED NOT NULL DEFAULT 0,
  failed_items INT UNSIGNED NOT NULL DEFAULT 0,
  skipped_items INT UNSIGNED NOT NULL DEFAULT 0,
  info_items INT UNSIGNED NOT NULL DEFAULT 0,
  total_latency_ms INT UNSIGNED NULL,
  status ENUM('running','passed','failed','partial') NOT NULL DEFAULT 'running',
  notes TEXT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS benchmark_items (
  id INT NOT NULL AUTO_INCREMENT,
  run_id INT NOT NULL,
  category ENUM('system','ai','perf') NOT NULL,
  item_no INT UNSIGNED NOT NULL,
  item_key VARCHAR(64) NOT NULL,
  label VARCHAR(255) NOT NULL,
  status ENUM('passed','failed','skipped','info','running') NOT NULL DEFAULT 'running',
  value_ms INT UNSIGNED NULL,
  value_text VARCHAR(255) NULL,
  message TEXT NULL,
  evidence_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_bm_items_run (run_id, item_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS model_plans (
  id INT NOT NULL AUTO_INCREMENT,
  hardware_profile_id BIGINT NULL,
  fingerprint CHAR(64) NOT NULL,
  schema_version SMALLINT NOT NULL DEFAULT 2,
  bootstrap_base_id VARCHAR(128) NOT NULL,
  bootstrap_params_b DECIMAL(6,2) NOT NULL,
  bootstrap_license VARCHAR(64) NULL,
  external_download_policy VARCHAR(32) NOT NULL DEFAULT 'cold-start-only',
  train_trainable TINYINT(1) NOT NULL DEFAULT 0,
  train_method VARCHAR(16) NOT NULL,
  train_device VARCHAR(16) NOT NULL,
  train_precision VARCHAR(16) NULL,
  train_lora_rank INT NOT NULL DEFAULT 0,
  train_lora_alpha INT NOT NULL DEFAULT 0,
  train_lora_dropout DECIMAL(5,3) NOT NULL DEFAULT 0.000,
  train_per_dev_batch INT NOT NULL DEFAULT 1,
  train_grad_accum_steps INT NOT NULL DEFAULT 1,
  train_effective_batch INT NOT NULL DEFAULT 1,
  train_seq_len INT NOT NULL DEFAULT 512,
  train_grad_checkpointing TINYINT(1) NOT NULL DEFAULT 0,
  train_optimizer VARCHAR(32) NULL,
  train_n_threads INT NOT NULL DEFAULT 2,
  train_max_params_b DECIMAL(6,2) NOT NULL DEFAULT 1.50,
  train_disabled_reason VARCHAR(255) NULL,
  infer_device VARCHAR(16) NOT NULL,
  infer_n_ctx INT NOT NULL,
  infer_n_batch INT NOT NULL,
  infer_n_threads INT NOT NULL,
  infer_n_gpu_layers INT NOT NULL DEFAULT 0,
  infer_max_concurrency SMALLINT NOT NULL DEFAULT 1,
  summary VARCHAR(512) NULL,
  raw_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.05.01-runtime-repair', 'Runtime schema repair for existing partially initialized databases');

DROP PROCEDURE add_col_if_missing;
