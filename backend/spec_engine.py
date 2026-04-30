"""Step 16: 명세서 기반 SW 생성 엔진 (휴리스틱 + LLM 후처리).

사진 명세 흐름::

    명세서 입력
        ↓
    요구사항 추출
        ↓
    기능 목록 생성
        ↓
    화면 목록 생성
        ↓
    API 목록 생성
        ↓
    DB 테이블 초안 생성
        ↓
    프로젝트 구조 생성
        ↓
    코드 생성

중간 데이터 JSON 스키마(사진과 1:1)::

    {
      "project_name": "...",
      "features": [],
      "screens": [],
      "apis": [],
      "database_tables": [],
      "business_rules": []
    }

본 모듈은 LLM 호출 없이 동작하는 *규칙 기반* 추출기 + 코드 스캐폴딩을 제공한다.
LLM 응답이 있으면 ``merge_llm_intermediate`` 로 결과를 합칠 수 있다.
"""
from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
EMPTY_INTERMEDIATE: dict[str, Any] = {
    "project_name":    "",
    "features":        [],
    "screens":         [],
    "apis":            [],
    "database_tables": [],
    "business_rules":  [],
}

STEP_LABELS: list[tuple[int, str, str]] = [
    (1, "spec_input",        "명세서 입력"),
    (2, "requirements",      "요구사항 추출"),
    (3, "features",          "기능 목록 생성"),
    (4, "screens",           "화면 목록 생성"),
    (5, "apis",              "API 목록 생성"),
    (6, "database_tables",   "DB 테이블 초안 생성"),
    (7, "project_structure", "프로젝트 구조 생성"),
    (8, "code_generation",   "코드 생성"),
]


# ---------------------------------------------------------------------------
# 1) 요구사항 추출 (명세서 → bullet list)
# ---------------------------------------------------------------------------
_BULLET_RE = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s+(.+)$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+)$")
_SENTENCE_SPLIT = re.compile(r"(?<=[\.\?!。?!])\s+|\n+")


def extract_requirements(text: str) -> list[str]:
    """명세서 본문에서 요구사항 후보 문장을 뽑는다.

    - bullet/numbered list 우선
    - 없으면 문장 단위 분리
    - 너무 짧거나 코드/구분선은 제거
    """
    if not text:
        return []
    items: list[str] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        m = _BULLET_RE.match(line)
        if m:
            items.append(m.group(1).strip())

    if not items:
        # 문장 분리 폴백
        for s in _SENTENCE_SPLIT.split(text):
            s = s.strip()
            if 8 <= len(s) <= 280 and not s.startswith("```"):
                items.append(s)

    # 중복/너무 짧은 항목 제거
    dedup: list[str] = []
    seen: set[str] = set()
    for it in items:
        norm = re.sub(r"\s+", " ", it).strip(" -•·\t")
        if len(norm) < 4 or norm in seen:
            continue
        seen.add(norm)
        dedup.append(norm)
    return dedup[:64]


def guess_project_name(text: str, fallback: str = "generated_project") -> str:
    """명세서 첫 헤딩 / 첫 줄에서 프로젝트 이름 추출."""
    if not text:
        return fallback
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            return _slug(m.group(1)) or fallback
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return _slug(first[:48]) or fallback


def _slug(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-z\uac00-\ud7a3 _\-]", "", s).strip()
    s = re.sub(r"\s+", "_", s).lower()
    return s[:48]


# ---------------------------------------------------------------------------
# 2) 기능/화면/API/DB/규칙 후보 추출
# ---------------------------------------------------------------------------
_KEYWORDS = {
    "feature":  ("기능", "feature", "function", "유스케이스", "use case", "동작"),
    "screen":   ("화면", "페이지", "스크린", "screen", "page", "view", "ui"),
    "api":      ("api", "엔드포인트", "endpoint", "라우트", "route"),
    "table":    ("테이블", "엔티티", "table", "entity", "도메인", "model", "스키마"),
    "rule":     ("규칙", "정책", "제약", "조건", "rule", "policy", "constraint"),
}

_HTTP_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[A-Za-z0-9_\-\{\}/:.\?]+)",
    re.IGNORECASE,
)


def _classify(req: str) -> str:
    low = req.lower()
    if _HTTP_RE.search(req):
        return "api"
    for kind, words in _KEYWORDS.items():
        for w in words:
            if w in low:
                return kind
    return "feature"


def derive_features(requirements: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(requirements, start=1):
        if _classify(r) in {"feature", "rule"}:
            out.append({
                "id":   f"F{i:03d}",
                "name": r[:80],
                "description": r,
            })
    if not out and requirements:
        out = [{"id": f"F{i:03d}", "name": r[:80], "description": r}
               for i, r in enumerate(requirements[:8], start=1)]
    return out


def derive_screens(requirements: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(requirements, start=1):
        if _classify(r) == "screen":
            out.append({
                "id":   f"S{i:03d}",
                "name": r[:60],
                "route": "/" + _slug(r[:24] or f"screen_{i}"),
                "description": r,
            })
    return out


def derive_apis(requirements: list[str], full_text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # 1) 본문 + 요구사항에서 HTTP 라인 직접 추출
    for src in [full_text or ""] + requirements:
        for m in _HTTP_RE.finditer(src):
            method = m.group(1).upper()
            path = m.group(2)
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "id":     f"A{len(out)+1:03d}",
                "method": method,
                "path":   path,
                "summary": f"{method} {path}",
            })

    # 2) requirement 가 'api' 로 분류되었지만 HTTP 표기가 없으면 자동 명명
    for i, r in enumerate(requirements, start=1):
        if _classify(r) == "api" and not _HTTP_RE.search(r):
            path = "/" + _slug(r[:24] or f"endpoint_{i}")
            key = ("POST", path)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "id":     f"A{len(out)+1:03d}",
                "method": "POST",
                "path":   path,
                "summary": r[:120],
            })
    return out


def derive_database_tables(requirements: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, r in enumerate(requirements, start=1):
        if _classify(r) != "table":
            continue
        # 요구사항에서 테이블 후보 명사 추출 (한글/영문 단어 첫 토큰)
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]+|[\uac00-\ud7a3]+", r)
        name = (tokens[0] if tokens else f"table_{i}").lower()
        name = _slug(name) or f"table_{i}"
        if name in seen:
            continue
        seen.add(name)
        out.append({
            "id":   f"T{len(out)+1:03d}",
            "name": name,
            "columns": [
                {"name": "id",         "type": "BIGINT",       "pk": True, "auto_increment": True},
                {"name": "created_at", "type": "TIMESTAMP",    "default": "CURRENT_TIMESTAMP"},
            ],
            "description": r,
        })
    return out


def derive_business_rules(requirements: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(requirements, start=1):
        low = r.lower()
        if any(w in low for w in _KEYWORDS["rule"]) or "must" in low or "shall" in low:
            out.append({"id": f"R{len(out)+1:03d}", "rule": r})
    return out


# ---------------------------------------------------------------------------
# 3) 전체 중간 JSON 빌드
# ---------------------------------------------------------------------------
def build_intermediate(
    text: str,
    *,
    project_name: str | None = None,
) -> dict[str, Any]:
    """사진의 중간 데이터 JSON 을 규칙 기반으로 만든다."""
    reqs = extract_requirements(text)
    return {
        "project_name":    project_name or guess_project_name(text),
        "features":        derive_features(reqs),
        "screens":         derive_screens(reqs),
        "apis":            derive_apis(reqs, text),
        "database_tables": derive_database_tables(reqs),
        "business_rules":  derive_business_rules(reqs),
        "_requirements":   reqs,
    }


# ---------------------------------------------------------------------------
# 4) LLM JSON 파싱 / 머지
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.+?)```", re.DOTALL)


def parse_llm_json(text: str | None) -> dict[str, Any] | None:
    """LLM 응답에서 JSON 블록을 추출한다.

    - ``` ... ``` 펜스 우선
    - 첫 ``{`` ~ 마지막 ``}`` 폴백
    """
    if not text:
        return None
    m = _FENCE_RE.search(text)
    candidate = m.group(1) if m else None
    if candidate is None:
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e != -1 and e > s:
            candidate = text[s : e + 1]
    if not candidate:
        return None
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def merge_llm_intermediate(
    base: dict[str, Any],
    llm_json: dict[str, Any] | None,
) -> dict[str, Any]:
    """규칙 기반 base 위에 LLM JSON 을 *덮어쓰기*. LLM 결과를 우선한다."""
    if not llm_json:
        return base
    out = dict(base)
    if llm_json.get("project_name"):
        out["project_name"] = str(llm_json["project_name"])
    for key in ("features", "screens", "apis", "database_tables", "business_rules"):
        val = llm_json.get(key)
        if isinstance(val, list) and val:
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# 5) 프로젝트 구조 + 코드 생성 (FastAPI 기준 기본 스캐폴드)
# ---------------------------------------------------------------------------
def derive_project_structure(
    intermediate: dict[str, Any],
    *,
    language: str = "python",
    framework: str = "fastapi",
) -> dict[str, Any]:
    """사진의 '프로젝트 구조 생성' 박스. 디렉토리 트리 dict 를 반환."""
    name = _slug(intermediate.get("project_name") or "generated_project") or "generated_project"
    if framework == "fastapi":
        tree = {
            "root": name,
            "directories": [
                "app", "app/api", "app/models", "app/schemas",
                "app/services", "app/db", "tests",
            ],
            "files": [
                "README.md",
                "requirements.txt",
                ".env.example",
                "app/__init__.py",
                "app/main.py",
                "app/api/__init__.py",
                "app/api/routes.py",
                "app/models/__init__.py",
                "app/models/tables.py",
                "app/schemas/__init__.py",
                "app/schemas/dto.py",
                "app/services/__init__.py",
                "app/db/__init__.py",
                "app/db/session.py",
                "tests/test_smoke.py",
            ],
        }
    else:
        tree = {
            "root": name,
            "directories": ["src", "tests"],
            "files": ["README.md", "src/main.py", "tests/test_smoke.py"],
        }
    return {
        "language": language,
        "framework": framework,
        "tree": tree,
    }


def _py_class_name(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_]+", "_", s)
    parts = [p for p in s.split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Model"


def _python_table_class(table: dict[str, Any]) -> str:
    cls = _py_class_name(table.get("name") or "Model")
    cols = table.get("columns") or []
    lines = [f"class {cls}:"]
    lines.append(f'    """Auto-generated from spec table {table.get("name")}."""')
    if not cols:
        lines.append("    pass")
    else:
        lines.append("    def __init__(self):")
        if not cols:
            lines.append("        pass")
        for c in cols:
            lines.append(f"        self.{c.get('name', 'field')} = None  # {c.get('type', '')}")
    return "\n".join(lines)


def generate_project_files(
    intermediate: dict[str, Any],
    *,
    language: str = "python",
    framework: str = "fastapi",
) -> list[dict[str, Any]]:
    """사진의 '코드 생성' 박스. 파일 목록(rel_path/code/role/language) 을 반환한다."""
    name = _slug(intermediate.get("project_name") or "generated_project") or "generated_project"
    apis     = intermediate.get("apis") or []
    tables   = intermediate.get("database_tables") or []
    features = intermediate.get("features") or []
    screens  = intermediate.get("screens") or []
    rules    = intermediate.get("business_rules") or []

    files: list[dict[str, Any]] = []

    # README.md
    def _bullets(items: list[str]) -> list[str]:
        return items if items else ["- (none)"]

    md_lines = [
        f"# {name}",
        "",
        "> Auto-generated by local-ai Step 16 spec engine.",
        "",
        "## Features",
        *_bullets([f"- ({f.get('id', '')}) {f.get('name', '')}" for f in features]),
        "",
        "## Screens",
        *_bullets([f"- ({s.get('id', '')}) {s.get('name', '')} → `{s.get('route', '')}`" for s in screens]),
        "",
        "## APIs",
        *_bullets([f"- {a.get('method', 'GET')} `{a.get('path', '/')}` — {a.get('summary', '')}" for a in apis]),
        "",
        "## Database Tables",
        *_bullets([f"- `{t.get('name', '')}` ({len(t.get('columns') or [])} cols)" for t in tables]),
        "",
        "## Business Rules",
        *_bullets([f"- ({r.get('id', '')}) {r.get('rule', '')}" for r in rules]),
        "",
    ]
    files.append({
        "rel_path": "README.md",
        "language": "markdown",
        "role":     "docs",
        "code":     "\n".join(md_lines),
    })

    if framework != "fastapi":
        files.append({
            "rel_path": "src/main.py",
            "language": language,
            "role":     "backend",
            "code":     f'"""Entry point for {name}."""\n\n\ndef main():\n    print("hello {name}")\n\n\nif __name__ == "__main__":\n    main()\n',
        })
        return files

    # ---- FastAPI 기본 스캐폴드 ----
    files.append({
        "rel_path": "requirements.txt",
        "language": "text",
        "role":     "config",
        "code":     "fastapi\nuvicorn[standard]\npydantic\n",
    })
    files.append({
        "rel_path": ".env.example",
        "language": "ini",
        "role":     "config",
        "code":     f"# {name} environment\nAPP_NAME={name}\nLOG_LEVEL=INFO\n",
    })
    files.append({
        "rel_path": "app/__init__.py",
        "language": "python",
        "role":     "backend",
        "code":     f'"""{name} package."""\n',
    })

    # main.py
    main_code = (
        '"""Auto-generated FastAPI entrypoint (Step 16 spec engine)."""\n'
        "from fastapi import FastAPI\n"
        "from app.api.routes import router\n\n"
        f'app = FastAPI(title="{name}")\n'
        'app.include_router(router)\n\n\n'
        '@app.get("/health")\n'
        "def health():\n"
        '    return {"status": "ok"}\n'
    )
    files.append({
        "rel_path": "app/main.py",
        "language": "python",
        "role":     "backend",
        "code":     main_code,
    })

    # routes.py — API 목록을 그대로 stub 라우트로 펼친다
    route_lines = [
        '"""Auto-generated API routes (Step 16 spec engine)."""',
        "from fastapi import APIRouter",
        "",
        "router = APIRouter()",
        "",
    ]
    if not apis:
        route_lines += [
            '@router.get("/api/ping")',
            "def ping():",
            '    return {"pong": True}',
            "",
        ]
    else:
        used: set[str] = set()
        for i, a in enumerate(apis, start=1):
            method = (a.get("method") or "GET").lower()
            if method not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                method = "get"
            path = a.get("path") or f"/api/auto_{i}"
            if not path.startswith("/"):
                path = "/" + path
            fname = "handler_" + _slug(path.strip("/").replace("/", "_") or f"auto_{i}")
            base_fname = fname
            j = 2
            while fname in used:
                fname = f"{base_fname}_{j}"; j += 1
            used.add(fname)
            summary = (a.get("summary") or "").replace('"', "'")
            route_lines += [
                f'@router.{method}("{path}")',
                f"def {fname}():",
                f'    """{summary}"""',
                f'    return {{"endpoint": "{method.upper()} {path}", "stub": True}}',
                "",
            ]
    files.append({
        "rel_path": "app/api/__init__.py",
        "language": "python",
        "role":     "backend",
        "code":     "",
    })
    files.append({
        "rel_path": "app/api/routes.py",
        "language": "python",
        "role":     "backend",
        "code":     "\n".join(route_lines),
    })

    # tables.py — 데이터베이스 테이블 dataclass-ish stub
    table_lines = [
        '"""Auto-generated DB models (Step 16 spec engine)."""',
        "",
    ]
    if not tables:
        table_lines += ["class _Empty:", "    pass", ""]
    else:
        for t in tables:
            table_lines.append(_python_table_class(t))
            table_lines.append("")
    files.append({
        "rel_path": "app/models/__init__.py",
        "language": "python",
        "role":     "db",
        "code":     "",
    })
    files.append({
        "rel_path": "app/models/tables.py",
        "language": "python",
        "role":     "db",
        "code":     "\n".join(table_lines),
    })

    # schemas/dto.py — 요구사항 기반 DTO 자리표시자
    files.append({
        "rel_path": "app/schemas/__init__.py",
        "language": "python",
        "role":     "backend",
        "code":     "",
    })
    files.append({
        "rel_path": "app/schemas/dto.py",
        "language": "python",
        "role":     "backend",
        "code":     (
            '"""Auto-generated DTO placeholders (Step 16 spec engine)."""\n'
            "from pydantic import BaseModel\n\n"
            "class HealthResponse(BaseModel):\n"
            "    status: str = \"ok\"\n"
        ),
    })

    # services/db
    files.append({
        "rel_path": "app/services/__init__.py",
        "language": "python",
        "role":     "backend",
        "code":     "",
    })
    files.append({
        "rel_path": "app/db/__init__.py",
        "language": "python",
        "role":     "db",
        "code":     "",
    })
    files.append({
        "rel_path": "app/db/session.py",
        "language": "python",
        "role":     "db",
        "code":     (
            '"""Auto-generated DB session placeholder (Step 16 spec engine)."""\n'
            "def get_session():\n"
            "    raise NotImplementedError(\"connect to your database here\")\n"
        ),
    })

    # tests
    files.append({
        "rel_path": "tests/test_smoke.py",
        "language": "python",
        "role":     "test",
        "code":     (
            '"""Auto-generated smoke test (Step 16 spec engine)."""\n'
            "from fastapi.testclient import TestClient\n"
            "from app.main import app\n\n"
            "def test_health():\n"
            "    client = TestClient(app)\n"
            "    r = client.get(\"/health\")\n"
            "    assert r.status_code == 200\n"
        ),
    })

    return files


def summarize_intermediate(intermediate: dict[str, Any]) -> dict[str, int]:
    """대시보드/run 기록용 카운트 요약."""
    return {
        "feature_count": len(intermediate.get("features") or []),
        "screen_count":  len(intermediate.get("screens") or []),
        "api_count":     len(intermediate.get("apis") or []),
        "table_count":   len(intermediate.get("database_tables") or []),
        "rule_count":    len(intermediate.get("business_rules") or []),
    }
