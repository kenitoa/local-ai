-- local-ai 초기 DB 부트스트랩 (Step 2)
-- 빈 DB 검증용. 실제 스키마는 Backend 단계에서 추가됩니다.
CREATE DATABASE IF NOT EXISTS localai_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE localai_db;

CREATE TABLE IF NOT EXISTS health_check (
  id INT AUTO_INCREMENT PRIMARY KEY,
  status VARCHAR(16) NOT NULL DEFAULT 'ok',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO health_check (status) VALUES ('ok');
