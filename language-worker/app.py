"""local-ai language-worker.

Step 8: 단순 언어 감지 (`/api/v1/detect`).
Step 9: 모든 언어 호환 계층 (Language Compatibility Layer)
        - 언어 자동 감지 (확장자 + 내용 패턴 + shebang)
        - 코드 패턴/주석 스타일 분석
        - import / include / use / package 분석
        - 함수/클래스 추출
        - dependency 파일 탐지
        - 빌드/실행 명령어 추론
        - 언어별 adapter 연결
        - 지원 등급(Level 1~6) 표시
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

SERVICE_NAME = os.getenv("SERVICE_NAME", "language-worker")
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"{SERVICE_NAME}.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=f"local-ai {SERVICE_NAME}")


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def _startup():
    log.info("%s service started", SERVICE_NAME)


# ===========================================================================
# Step 9: Language Compatibility Layer
# ---------------------------------------------------------------------------
# LANGUAGE_REGISTRY 는 한 언어의 모든 정보(확장자/주석/import 패턴/함수·클래스
# 추출 정규식 / dependency 파일명 / 빌드·실행 명령어 / adapter 식별자 /
# 지원 등급)를 한 곳에 모은 카탈로그이다. 새 언어를 추가하려면 이 표에만
# 행을 추가하면 된다.
# ===========================================================================

# 지원 등급 정의 (사진의 표 기준)
SUPPORT_LEVELS = {
    1: "언어 감지, 코드 입력 가능",
    2: "함수/클래스 구조 추출",
    3: "라이브러리 사용 분석",
    4: "최적화 제안",
    5: "실행/테스트",
    6: "명세서 기반 코드 생성",
}


def _re(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p, re.MULTILINE) for p in patterns]


LANGUAGE_REGISTRY: dict[str, dict[str, Any]] = {
    # --- MVP 주요 언어 (Level 4 이상 목표) -------------------------------
    "python": {
        "extensions": [".py", ".pyw", ".pyi"],
        "filenames":  ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"],
        "shebangs":   ["python", "python3"],
        "comment":    {"line": "#", "block": ('"""', '"""')},
        "patterns":   _re(r"^\s*def\s+\w+\s*\(", r"^\s*from\s+\w+\s+import",
                          r"^\s*import\s+\w+", r"\bprint\s*\(", r":\s*$"),
        "import_re":  _re(r"^\s*import\s+([\w\.]+)", r"^\s*from\s+([\w\.]+)\s+import"),
        "function_re": _re(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\("),
        "class_re":    _re(r"^\s*class\s+([A-Za-z_]\w*)"),
        "dep_files":   ["requirements.txt", "pyproject.toml", "Pipfile", "setup.py"],
        "build":       "pip install -r requirements.txt",
        "run":         "python {file}",
        "test":        "pytest",
        "adapter":     "python-adapter",
        "level":       5,
    },
    "javascript": {
        "extensions": [".js", ".mjs", ".cjs"],
        "filenames":  ["package.json", "package-lock.json", "yarn.lock"],
        "shebangs":   ["node"],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\bfunction\s+\w+\s*\(", r"\bconst\s+\w+\s*=",
                          r"=>\s*\{", r"\bconsole\.log\s*\("),
        "import_re":  _re(r"^\s*import\s+.*from\s+['\"]([^'\"]+)['\"]",
                          r"\brequire\(['\"]([^'\"]+)['\"]\)"),
        "function_re": _re(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(",
                           r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\("),
        "class_re":    _re(r"\bclass\s+([A-Za-z_$][\w$]*)"),
        "dep_files":   ["package.json"],
        "build":       "npm install",
        "run":         "node {file}",
        "test":        "npm test",
        "adapter":     "node-adapter",
        "level":       5,
    },
    "typescript": {
        "extensions": [".ts", ".tsx"],
        "filenames":  ["tsconfig.json", "package.json"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r":\s*(?:string|number|boolean)\b", r"\binterface\s+\w+",
                          r"\btype\s+\w+\s*=", r"\bexport\s+(?:default\s+)?(?:class|function|const)"),
        "import_re":  _re(r"^\s*import\s+.*from\s+['\"]([^'\"]+)['\"]"),
        "function_re": _re(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(",
                           r"\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*\("),
        "class_re":    _re(r"\bclass\s+([A-Za-z_$][\w$]*)",
                           r"\binterface\s+([A-Za-z_$][\w$]*)"),
        "dep_files":   ["package.json", "tsconfig.json"],
        "build":       "npm install && tsc",
        "run":         "ts-node {file}",
        "test":        "npm test",
        "adapter":     "node-adapter",
        "level":       4,
    },
    "java": {
        "extensions": [".java"],
        "filenames":  ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\bpublic\s+(?:class|static)\b", r"System\.out\.println",
                          r"\bpackage\s+[\w\.]+;"),
        "import_re":  _re(r"^\s*import\s+([\w\.]+);"),
        "function_re": _re(r"\b(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\([^;{]*\{"),
        "class_re":    _re(r"\b(?:public\s+|abstract\s+|final\s+)*class\s+([A-Za-z_]\w*)",
                           r"\binterface\s+([A-Za-z_]\w*)"),
        "dep_files":   ["pom.xml", "build.gradle", "build.gradle.kts"],
        "build":       "mvn package",
        "run":         "java {class}",
        "test":        "mvn test",
        "adapter":     "jvm-adapter",
        "level":       4,
    },
    "cpp": {
        "extensions": [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh", ".h++"],
        "filenames":  ["CMakeLists.txt", "Makefile", "meson.build"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"#include\s*<[\w\./]+>", r"std::",
                          r"\btemplate\s*<", r"\busing\s+namespace\b"),
        "import_re":  _re(r"#include\s*[<\"]([\w\./]+)[>\"]"),
        "function_re": _re(r"^[\w:<>,\*\&\s]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{"),
        "class_re":    _re(r"\b(?:class|struct)\s+([A-Za-z_]\w*)"),
        "dep_files":   ["CMakeLists.txt", "Makefile", "vcpkg.json", "conanfile.txt"],
        "build":       "cmake -B build && cmake --build build",
        "run":         "./build/{name}",
        "test":        "ctest --test-dir build",
        "adapter":     "cpp-adapter",
        "level":       4,
    },
    "c": {
        "extensions": [".c", ".h"],
        "filenames":  ["Makefile", "CMakeLists.txt"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"#include\s*<\w+\.h>", r"\bprintf\s*\(", r"\bint\s+main\s*\("),
        "import_re":  _re(r"#include\s*[<\"]([\w\./]+)[>\"]"),
        "function_re": _re(r"^[\w\*\s]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{"),
        "class_re":    _re(r"\bstruct\s+([A-Za-z_]\w*)"),
        "dep_files":   ["Makefile", "CMakeLists.txt"],
        "build":       "make",
        "run":         "./{name}",
        "test":        "make test",
        "adapter":     "c-adapter",
        "level":       4,
    },
    "go": {
        "extensions": [".go"],
        "filenames":  ["go.mod", "go.sum"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\bpackage\s+\w+\b", r"\bfunc\s+\w+", r"\bfmt\."),
        "import_re":  _re(r'^\s*import\s+"([^"]+)"', r'^\s+"([^"]+)"'),
        "function_re": _re(r"\bfunc\s+(?:\([^)]*\)\s+)?([A-Za-z_]\w*)\s*\("),
        "class_re":    _re(r"\btype\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b"),
        "dep_files":   ["go.mod"],
        "build":       "go build ./...",
        "run":         "go run {file}",
        "test":        "go test ./...",
        "adapter":     "go-adapter",
        "level":       5,
    },
    "rust": {
        "extensions": [".rs"],
        "filenames":  ["Cargo.toml", "Cargo.lock"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\bfn\s+\w+\s*\(", r"\blet\s+(?:mut\s+)?\w+",
                          r"\bprintln!\s*\(", r"::<"),
        "import_re":  _re(r"^\s*use\s+([\w:]+)"),
        "function_re": _re(r"\bfn\s+([A-Za-z_]\w*)\s*[<\(]"),
        "class_re":    _re(r"\b(?:struct|enum|trait)\s+([A-Za-z_]\w*)"),
        "dep_files":   ["Cargo.toml"],
        "build":       "cargo build",
        "run":         "cargo run",
        "test":        "cargo test",
        "adapter":     "rust-adapter",
        "level":       5,
    },
    "csharp": {
        "extensions": [".cs"],
        "filenames":  ["*.csproj", "*.sln", "global.json"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\busing\s+System", r"\bnamespace\s+\w+",
                          r"Console\.WriteLine"),
        "import_re":  _re(r"^\s*using\s+([\w\.]+);"),
        "function_re": _re(r"\b(?:public|private|protected|internal|static|\s)+[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{"),
        "class_re":    _re(r"\b(?:class|interface|struct|record)\s+([A-Za-z_]\w*)"),
        "dep_files":   ["*.csproj", "packages.config"],
        "build":       "dotnet build",
        "run":         "dotnet run",
        "test":        "dotnet test",
        "adapter":     "dotnet-adapter",
        "level":       4,
    },
    "kotlin": {
        "extensions": [".kt", ".kts"],
        "filenames":  ["build.gradle.kts", "build.gradle", "settings.gradle.kts"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\bfun\s+\w+\s*\(", r"\bval\s+\w+\s*=",
                          r"\bvar\s+\w+\s*:"),
        "import_re":  _re(r"^\s*import\s+([\w\.]+)"),
        "function_re": _re(r"\bfun\s+([A-Za-z_]\w*)\s*\("),
        "class_re":    _re(r"\b(?:class|object|interface)\s+([A-Za-z_]\w*)"),
        "dep_files":   ["build.gradle.kts", "build.gradle"],
        "build":       "gradle build",
        "run":         "gradle run",
        "test":        "gradle test",
        "adapter":     "jvm-adapter",
        "level":       3,
    },
    "swift": {
        "extensions": [".swift"],
        "filenames":  ["Package.swift", "Podfile"],
        "shebangs":   [],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"\bfunc\s+\w+\s*\(", r"\blet\s+\w+\s*=",
                          r"\bprint\s*\("),
        "import_re":  _re(r"^\s*import\s+([\w\.]+)"),
        "function_re": _re(r"\bfunc\s+([A-Za-z_]\w*)\s*\("),
        "class_re":    _re(r"\b(?:class|struct|enum|protocol)\s+([A-Za-z_]\w*)"),
        "dep_files":   ["Package.swift", "Podfile"],
        "build":       "swift build",
        "run":         "swift run",
        "test":        "swift test",
        "adapter":     "swift-adapter",
        "level":       2,
    },
    "ruby": {
        "extensions": [".rb"],
        "filenames":  ["Gemfile", "Gemfile.lock", "Rakefile"],
        "shebangs":   ["ruby"],
        "comment":    {"line": "#", "block": ("=begin", "=end")},
        "patterns":   _re(r"\bdef\s+\w+", r"\bputs\s+", r"\bend\s*$",
                          r"\brequire\s+['\"][\w\-/]+['\"]"),
        "import_re":  _re(r"^\s*require\s+['\"]([^'\"]+)['\"]",
                          r"^\s*require_relative\s+['\"]([^'\"]+)['\"]"),
        "function_re": _re(r"\bdef\s+(?:self\.)?([A-Za-z_]\w*)"),
        "class_re":    _re(r"\b(?:class|module)\s+([A-Za-z_][\w:]*)"),
        "dep_files":   ["Gemfile"],
        "build":       "bundle install",
        "run":         "ruby {file}",
        "test":        "rspec",
        "adapter":     "ruby-adapter",
        "level":       3,
    },
    "php": {
        "extensions": [".php"],
        "filenames":  ["composer.json", "composer.lock"],
        "shebangs":   ["php"],
        "comment":    {"line": "//", "block": ("/*", "*/")},
        "patterns":   _re(r"<\?php", r"\bfunction\s+\w+\s*\(",
                          r"\$\w+\s*=", r"\becho\s+"),
        "import_re":  _re(r"^\s*use\s+([\w\\]+);",
                          r"\brequire(?:_once)?\s*\(?['\"]([^'\"]+)['\"]"),
        "function_re": _re(r"\bfunction\s+([A-Za-z_]\w*)\s*\("),
        "class_re":    _re(r"\b(?:class|interface|trait)\s+([A-Za-z_]\w*)"),
        "dep_files":   ["composer.json"],
        "build":       "composer install",
        "run":         "php {file}",
        "test":        "phpunit",
        "adapter":     "php-adapter",
        "level":       3,
    },
    "shell": {
        "extensions": [".sh", ".bash", ".zsh"],
        "filenames":  ["Makefile"],
        "shebangs":   ["sh", "bash", "zsh"],
        "comment":    {"line": "#", "block": None},
        "patterns":   _re(r"^#!/bin/(?:ba|z)?sh", r"\becho\s+",
                          r"\bif\s+\[", r"\bfi\s*$"),
        "import_re":  _re(r"^\s*(?:source|\.)\s+([\w\./\-]+)"),
        "function_re": _re(r"^\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\s*\)\s*\{"),
        "class_re":    [],
        "dep_files":   [],
        "build":       "",
        "run":         "bash {file}",
        "test":        "bats",
        "adapter":     "shell-adapter",
        "level":       2,
    },
    "sql": {
        "extensions": [".sql"],
        "filenames":  [],
        "shebangs":   [],
        "comment":    {"line": "--", "block": ("/*", "*/")},
        "patterns":   _re(r"\bSELECT\b.*\bFROM\b", r"\bINSERT\s+INTO\b",
                          r"\bCREATE\s+TABLE\b", r"\bUPDATE\b.*\bSET\b"),
        "import_re":  [],
        "function_re": _re(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([A-Za-z_]\w*)"),
        "class_re":    _re(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)"),
        "dep_files":   [],
        "build":       "",
        "run":         "",
        "test":        "",
        "adapter":     "sql-adapter",
        "level":       2,
    },
    "html": {
        "extensions": [".html", ".htm"],
        "filenames":  [],
        "shebangs":   [],
        "comment":    {"line": None, "block": ("<!--", "-->")},
        "patterns":   _re(r"<!doctype\s+html>", r"<html", r"<body", r"<div"),
        "import_re":  _re(r"<script[^>]*src=['\"]([^'\"]+)['\"]",
                          r"<link[^>]*href=['\"]([^'\"]+)['\"]"),
        "function_re": [],
        "class_re":    [],
        "dep_files":   [],
        "build":       "",
        "run":         "",
        "test":        "",
        "adapter":     "static-adapter",
        "level":       1,
    },
    "css": {
        "extensions": [".css", ".scss", ".sass", ".less"],
        "filenames":  [],
        "shebangs":   [],
        "comment":    {"line": None, "block": ("/*", "*/")},
        "patterns":   _re(r"^\s*\.[\w\-]+\s*\{", r"^\s*#[\w\-]+\s*\{",
                          r":\s*[\w#][^;]*;"),
        "import_re":  _re(r"@import\s+['\"]([^'\"]+)['\"]"),
        "function_re": [],
        "class_re":    _re(r"^\s*\.([\w\-]+)\s*\{"),
        "dep_files":   [],
        "build":       "",
        "run":         "",
        "test":        "",
        "adapter":     "static-adapter",
        "level":       1,
    },
}

# 빠른 lookup 테이블 ----------------------------------------------------------
EXTENSION_TO_LANG: dict[str, str] = {}
FILENAME_TO_LANG: dict[str, str] = {}
SHEBANG_TO_LANG: dict[str, str] = {}
for _lang, _info in LANGUAGE_REGISTRY.items():
    for _ext in _info["extensions"]:
        EXTENSION_TO_LANG[_ext.lower()] = _lang
    for _fn in _info["filenames"]:
        FILENAME_TO_LANG[_fn.lower()] = _lang
    for _sb in _info["shebangs"]:
        SHEBANG_TO_LANG[_sb.lower()] = _lang


# ---------------------------------------------------------------------------
# 보조 함수
# ---------------------------------------------------------------------------
def _detect_by_extension(filename: str | None) -> str | None:
    if not filename:
        return None
    name = filename.lower().strip()
    base = os.path.basename(name)
    if base in FILENAME_TO_LANG:
        return FILENAME_TO_LANG[base]
    for pat, lang in FILENAME_TO_LANG.items():
        if pat.startswith("*") and base.endswith(pat[1:]):
            return lang
    _, ext = os.path.splitext(base)
    return EXTENSION_TO_LANG.get(ext)


def _detect_by_shebang(code: str) -> str | None:
    first_line = (code.splitlines() or [""])[0]
    if not first_line.startswith("#!"):
        return None
    for sb, lang in SHEBANG_TO_LANG.items():
        if sb in first_line:
            return lang
    return None


def _score_by_patterns(code: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for lang, info in LANGUAGE_REGISTRY.items():
        s = 0
        for pat in info["patterns"]:
            if pat.search(code):
                s += 1
        if s > 0:
            scores[lang] = s
    return scores


def _detect_language(code: str, filename: str | None, hint: str | None) -> dict[str, Any]:
    """확장자 → shebang → 패턴 휴리스틱 순으로 결정."""
    if hint and hint.lower() in LANGUAGE_REGISTRY:
        return {"language": hint.lower(), "confidence": 1.0,
                "source": "hint", "scores": {}}

    by_ext = _detect_by_extension(filename)
    if by_ext:
        scores = _score_by_patterns(code)
        return {"language": by_ext,
                "confidence": min(1.0, 0.6 + 0.05 * scores.get(by_ext, 0)),
                "source": "extension", "scores": scores}

    by_shebang = _detect_by_shebang(code)
    if by_shebang:
        return {"language": by_shebang, "confidence": 0.95,
                "source": "shebang", "scores": _score_by_patterns(code)}

    scores = _score_by_patterns(code)
    if not scores:
        return {"language": "plain", "confidence": 0.0,
                "source": "fallback", "scores": {}}
    best = max(scores.items(), key=lambda kv: kv[1])
    total = sum(scores.values()) or 1
    return {"language": best[0],
            "confidence": round(best[1] / total, 3),
            "source": "heuristic", "scores": scores}


def _extract_imports(code: str, info: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for pat in info["import_re"]:
        for m in pat.finditer(code):
            val = m.group(1).strip()
            if val and val not in found:
                found.append(val)
    return found


def _extract_names(code: str, patterns: list[re.Pattern[str]]) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        for m in pat.finditer(code):
            name = m.group(1)
            if name and name not in out:
                out.append(name)
    return out


def _comment_density(code: str, info: dict[str, Any]) -> dict[str, Any]:
    line_marker = info["comment"].get("line") if info["comment"] else None
    block = info["comment"].get("block") if info["comment"] else None
    lines = code.splitlines() or [""]
    line_comments = 0
    if line_marker:
        line_comments = sum(1 for ln in lines if ln.strip().startswith(line_marker))
    block_comments = 0
    if block:
        start, _end = block
        block_comments = max(0, code.count(start))
    total = max(1, len(lines))
    return {
        "line_marker": line_marker,
        "block_marker": list(block) if block else None,
        "line_comment_count": line_comments,
        "block_comment_count": block_comments,
        "ratio": round((line_comments + block_comments) / total, 3),
    }


def _format_command(template: str, *, filename: str | None, language: str) -> str:
    if not template:
        return ""
    info = LANGUAGE_REGISTRY.get(language) or {}
    default_ext = info.get("extensions", [""])[0] if info else ""
    file_token = filename or (f"main{default_ext}" if default_ext else "main")
    name_token = os.path.splitext(os.path.basename(file_token))[0] or "app"
    class_token = (name_token[:1].upper() + name_token[1:]) if name_token else "App"
    return (template
            .replace("{file}", file_token)
            .replace("{name}", name_token)
            .replace("{class}", class_token))


# ---------------------------------------------------------------------------
# Pydantic 모델
# ---------------------------------------------------------------------------
class DetectIn(BaseModel):
    code: str
    filename: str | None = None
    hint: str | None = None


class AnalyzeIn(BaseModel):
    code: str
    filename: str | None = None
    hint: str | None = None
    include_patterns: bool = True


class GuessIn(BaseModel):
    filename: str


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------
@app.post("/api/v1/detect")
def detect(payload: DetectIn):
    """단순 언어 감지 - 기존 호환성 유지."""
    return _detect_language(payload.code or "", payload.filename, payload.hint)


@app.post("/api/v1/analyze")
def analyze(payload: AnalyzeIn):
    """Step 9: 모든 언어 호환 계층 - 통합 분석."""
    code = payload.code or ""
    detect_res = _detect_language(code, payload.filename, payload.hint)
    language = detect_res["language"]
    info = LANGUAGE_REGISTRY.get(language)

    if info is None:
        return {
            "language": language,
            "support_level": 1,
            "support_label": SUPPORT_LEVELS[1],
            "confidence": detect_res["confidence"],
            "detect": detect_res,
            "extension": os.path.splitext(payload.filename or "")[1] or None,
            "comment": None,
            "imports": [],
            "import_counts": {},
            "functions": [],
            "classes": [],
            "dependency_files": [],
            "build_command": "",
            "run_command": "",
            "test_command": "",
            "adapter": None,
            "stats": {
                "lines": len(code.splitlines()),
                "non_empty_lines": sum(1 for ln in code.splitlines() if ln.strip()),
                "characters": len(code),
                "imports": 0, "functions": 0, "classes": 0,
            },
        }

    imports   = _extract_imports(code, info)
    funcs     = _extract_names(code, info["function_re"])
    classes   = _extract_names(code, info["class_re"])
    comment   = _comment_density(code, info)
    dep_files = list(info["dep_files"])

    ext = os.path.splitext(payload.filename or "")[1] or info["extensions"][0]
    build_cmd = _format_command(info["build"], filename=payload.filename, language=language)
    run_cmd   = _format_command(info["run"],   filename=payload.filename, language=language)
    test_cmd  = _format_command(info["test"],  filename=payload.filename, language=language)

    import_counts: dict[str, int] = {}
    if payload.include_patterns and info["import_re"]:
        c: Counter[str] = Counter()
        for pat in info["import_re"]:
            for m in pat.finditer(code):
                c[m.group(1).strip()] += 1
        import_counts = dict(c.most_common(20))

    return {
        "language": language,
        "support_level": info["level"],
        "support_label": SUPPORT_LEVELS[info["level"]],
        "confidence": detect_res["confidence"],
        "detect": detect_res,
        "extension": ext,
        "comment": comment,
        "imports": imports,
        "import_counts": import_counts,
        "functions": funcs,
        "classes": classes,
        "dependency_files": dep_files,
        "build_command": build_cmd,
        "run_command": run_cmd,
        "test_command": test_cmd,
        "adapter": info["adapter"],
        "stats": {
            "lines": len(code.splitlines()),
            "non_empty_lines": sum(1 for ln in code.splitlines() if ln.strip()),
            "characters": len(code),
            "imports": len(imports),
            "functions": len(funcs),
            "classes": len(classes),
        },
    }


@app.get("/api/v1/languages")
def languages():
    """지원 언어 카탈로그 (Web UI 표시용)."""
    out = []
    for lang, info in LANGUAGE_REGISTRY.items():
        out.append({
            "language": lang,
            "extensions": info["extensions"],
            "dependency_files": info["dep_files"],
            "build": info["build"],
            "run": info["run"],
            "adapter": info["adapter"],
            "level": info["level"],
            "level_label": SUPPORT_LEVELS[info["level"]],
        })
    return {
        "support_levels": SUPPORT_LEVELS,
        "languages": sorted(out, key=lambda x: (-x["level"], x["language"])),
    }


@app.get("/api/v1/adapters")
def adapters():
    """언어별 adapter 식별자 (향후 실행/최적화 어댑터 연결용)."""
    by_adapter: dict[str, list[str]] = {}
    for lang, info in LANGUAGE_REGISTRY.items():
        by_adapter.setdefault(info["adapter"], []).append(lang)
    return {"adapters": by_adapter}


@app.post("/api/v1/guess-by-filename")
def guess_by_filename(payload: GuessIn):
    """파일명만으로 언어/빌드 명령을 빠르게 추론."""
    lang = _detect_by_extension(payload.filename)
    if not lang:
        return {"language": None}
    info = LANGUAGE_REGISTRY[lang]
    return {
        "language": lang,
        "level": info["level"],
        "adapter": info["adapter"],
        "build": info["build"],
        "run": _format_command(info["run"], filename=payload.filename, language=lang),
    }
