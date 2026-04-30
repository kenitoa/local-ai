-- =====================================================
-- local-ai Step 9 마이그레이션
--   목적: 모든 언어 호환 계층 (Language Compatibility Layer)
--   - language_profiles 에 지원 등급 / adapter / 빌드·실행 명령 컬럼 추가
--   - language_compat_seed : language-worker 의 카탈로그를 시드로 보존
--     (초기 시드는 language-worker /api/v1/languages 의 응답과 동기화)
-- =====================================================

USE localai_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------
-- language_profiles 확장 (Step 9)
-- -----------------------------------------------------
ALTER TABLE language_profiles
  ADD COLUMN IF NOT EXISTS support_level   TINYINT UNSIGNED NULL
    COMMENT '1: 감지/입력, 2: 함수·클래스 추출, 3: 라이브러리 분석, 4: 최적화 제안, 5: 실행/테스트, 6: 명세 기반 코드 생성',
  ADD COLUMN IF NOT EXISTS adapter         VARCHAR(64)   NULL
    COMMENT '연결되는 어댑터 식별자 (python-adapter 등)',
  ADD COLUMN IF NOT EXISTS extensions_json JSON          NULL
    COMMENT '확장자 리스트 (예: [".py", ".pyw"])',
  ADD COLUMN IF NOT EXISTS dep_files_json  JSON          NULL
    COMMENT 'dependency 파일명 리스트 (예: ["requirements.txt"])',
  ADD COLUMN IF NOT EXISTS build_cmd       VARCHAR(512)  NULL,
  ADD COLUMN IF NOT EXISTS run_cmd         VARCHAR(512)  NULL,
  ADD COLUMN IF NOT EXISTS test_cmd        VARCHAR(512)  NULL,
  ADD COLUMN IF NOT EXISTS comment_line    VARCHAR(8)    NULL,
  ADD COLUMN IF NOT EXISTS comment_block_open  VARCHAR(8) NULL,
  ADD COLUMN IF NOT EXISTS comment_block_close VARCHAR(8) NULL;

-- -----------------------------------------------------
-- 시드 데이터 (UNIQUE 키 (language, version) 사용 → version=NULL 회피용 'mvp')
-- language-worker LANGUAGE_REGISTRY 와 동기화
-- -----------------------------------------------------
INSERT INTO language_profiles
  (language, version, runtime, package_manager,
   support_level, adapter, extensions_json, dep_files_json,
   build_cmd, run_cmd, test_cmd,
   comment_line, comment_block_open, comment_block_close)
VALUES
  ('python',     'mvp', 'cpython', 'pip',      5, 'python-adapter',
   JSON_ARRAY('.py','.pyw','.pyi'), JSON_ARRAY('requirements.txt','pyproject.toml','Pipfile'),
   'pip install -r requirements.txt', 'python {file}', 'pytest', '#', '"""', '"""'),
  ('javascript', 'mvp', 'node',    'npm',      5, 'node-adapter',
   JSON_ARRAY('.js','.mjs','.cjs'), JSON_ARRAY('package.json'),
   'npm install', 'node {file}', 'npm test', '//', '/*', '*/'),
  ('typescript', 'mvp', 'node',    'npm',      4, 'node-adapter',
   JSON_ARRAY('.ts','.tsx'),       JSON_ARRAY('package.json','tsconfig.json'),
   'npm install && tsc', 'ts-node {file}', 'npm test', '//', '/*', '*/'),
  ('java',       'mvp', 'jvm',     'maven',    4, 'jvm-adapter',
   JSON_ARRAY('.java'),            JSON_ARRAY('pom.xml','build.gradle'),
   'mvn package', 'java {class}', 'mvn test', '//', '/*', '*/'),
  ('cpp',        'mvp', 'native',  'cmake',    4, 'cpp-adapter',
   JSON_ARRAY('.cpp','.cxx','.cc','.hpp'), JSON_ARRAY('CMakeLists.txt','Makefile'),
   'cmake -B build && cmake --build build', './build/{name}', 'ctest --test-dir build', '//', '/*', '*/'),
  ('c',          'mvp', 'native',  'make',     4, 'c-adapter',
   JSON_ARRAY('.c','.h'),          JSON_ARRAY('Makefile','CMakeLists.txt'),
   'make', './{name}', 'make test', '//', '/*', '*/'),
  ('go',         'mvp', 'go',      'gomod',    5, 'go-adapter',
   JSON_ARRAY('.go'),              JSON_ARRAY('go.mod'),
   'go build ./...', 'go run {file}', 'go test ./...', '//', '/*', '*/'),
  ('rust',       'mvp', 'rust',    'cargo',    5, 'rust-adapter',
   JSON_ARRAY('.rs'),              JSON_ARRAY('Cargo.toml'),
   'cargo build', 'cargo run', 'cargo test', '//', '/*', '*/'),
  ('csharp',     'mvp', 'dotnet',  'nuget',    4, 'dotnet-adapter',
   JSON_ARRAY('.cs'),              JSON_ARRAY('*.csproj'),
   'dotnet build', 'dotnet run', 'dotnet test', '//', '/*', '*/'),
  ('kotlin',     'mvp', 'jvm',     'gradle',   3, 'jvm-adapter',
   JSON_ARRAY('.kt','.kts'),       JSON_ARRAY('build.gradle.kts','build.gradle'),
   'gradle build', 'gradle run', 'gradle test', '//', '/*', '*/'),
  ('swift',      'mvp', 'swift',   'spm',      2, 'swift-adapter',
   JSON_ARRAY('.swift'),           JSON_ARRAY('Package.swift'),
   'swift build', 'swift run', 'swift test', '//', '/*', '*/'),
  ('ruby',       'mvp', 'cruby',   'bundler',  3, 'ruby-adapter',
   JSON_ARRAY('.rb'),              JSON_ARRAY('Gemfile'),
   'bundle install', 'ruby {file}', 'rspec', '#', '=begin', '=end'),
  ('php',        'mvp', 'php',     'composer', 3, 'php-adapter',
   JSON_ARRAY('.php'),             JSON_ARRAY('composer.json'),
   'composer install', 'php {file}', 'phpunit', '//', '/*', '*/'),
  ('shell',      'mvp', 'bash',    NULL,       2, 'shell-adapter',
   JSON_ARRAY('.sh','.bash','.zsh'), JSON_ARRAY(),
   '', 'bash {file}', 'bats', '#', NULL, NULL),
  ('sql',        'mvp', 'mysql',   NULL,       2, 'sql-adapter',
   JSON_ARRAY('.sql'),             JSON_ARRAY(),
   '', '', '', '--', '/*', '*/'),
  ('html',       'mvp', NULL,      NULL,       1, 'static-adapter',
   JSON_ARRAY('.html','.htm'),     JSON_ARRAY(),
   '', '', '', NULL, '<!--', '-->'),
  ('css',        'mvp', NULL,      NULL,       1, 'static-adapter',
   JSON_ARRAY('.css','.scss','.sass','.less'), JSON_ARRAY(),
   '', '', '', NULL, '/*', '*/')
ON DUPLICATE KEY UPDATE
  runtime         = VALUES(runtime),
  package_manager = VALUES(package_manager),
  support_level   = VALUES(support_level),
  adapter         = VALUES(adapter),
  extensions_json = VALUES(extensions_json),
  dep_files_json  = VALUES(dep_files_json),
  build_cmd       = VALUES(build_cmd),
  run_cmd         = VALUES(run_cmd),
  test_cmd        = VALUES(test_cmd),
  comment_line    = VALUES(comment_line),
  comment_block_open  = VALUES(comment_block_open),
  comment_block_close = VALUES(comment_block_close);

-- -----------------------------------------------------
-- raw_inputs 에 분석 결과(언어/지원등급) 빠른 조회 컬럼
-- -----------------------------------------------------
ALTER TABLE raw_inputs
  ADD COLUMN IF NOT EXISTS detected_language VARCHAR(64) NULL
    COMMENT 'language-worker 가 감지한 언어',
  ADD COLUMN IF NOT EXISTS support_level     TINYINT UNSIGNED NULL
    COMMENT '해당 언어의 현재 지원 등급';

CREATE INDEX IF NOT EXISTS idx_raw_detected_lang ON raw_inputs (detected_language);

-- -----------------------------------------------------
-- 버전 기록
-- -----------------------------------------------------
INSERT IGNORE INTO schema_versions (version, note)
VALUES ('2026.04.30-step9', 'Step 9: language compatibility layer (extensions/adapter/build/run/test)');
