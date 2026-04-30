"""local-ai backend Step 15: 규칙 기반 코드 최적화 분석.

사진 명세 흐름의 "정적 분석" 박스를 담당한다. LLM에 들어가기 전에 9가지
최적화 유형(`optimization_types.type_key`) 중 어떤 문제가 있는지 규칙으로
탐지해서 LLM 프롬프트에 힌트로 전달하고, finding 자체는 DB에 영구 보존한다.

Finding 한 건의 표준 dict::

    {
        "type_key":   "loop",
        "source":     "rule",
        "severity":   "info" | "warn" | "error",
        "rule_id":    "PY-LOOP-001",
        "line_no":    12,
        "col_no":     None,
        "message":    "range(len(x)) 패턴은 enumerate(x) 로 단순화할 수 있습니다.",
        "suggestion": "for i, item in enumerate(x):",
        "snippet":    "for i in range(len(items)):",
    }
"""
from __future__ import annotations

import ast
import re
from typing import Any, Iterable

# 사진의 9가지 최적화 유형 키 (mysql/init/11_step15_optimize_engine.sql 와 1:1)
OPTIMIZATION_TYPE_KEYS: tuple[str, ...] = (
    "syntax_error", "typo", "dead_code", "loop", "memory",
    "library", "algorithm", "readability", "speed",
)

# 자주 보이는 오탈자 매핑 (식별자/표준 모듈/메서드)
COMMON_TYPOS: dict[str, str] = {
    "pirnt": "print",
    "prinln": "println",
    "lenght": "length",
    "recieve": "receive",
    "reciever": "receiver",
    "seperate": "separate",
    "seperator": "separator",
    "occured": "occurred",
    "successfull": "successful",
    "begining": "beginning",
    "definately": "definitely",
    "retrun": "return",
    "fucntion": "function",
    "fucn": "func",
    "lenghth": "length",
    "stirng": "string",
}

# 표준 / 빠른 라이브러리 대체 후보
LIBRARY_REPLACEMENTS: list[dict[str, str]] = [
    {"language": "python", "from": "simplejson",
     "to": "json (표준 라이브러리)",
     "reason": "표준 json 모듈로 대부분의 사용 사례를 커버할 수 있어 의존성을 줄일 수 있습니다."},
    {"language": "python", "from": "urllib2",
     "to": "httpx 또는 requests",
     "reason": "Python3 에서는 urllib2 가 없습니다. httpx (비동기 지원) 또는 requests 로 교체하세요."},
    {"language": "python", "from": "pandas",
     "to": "polars (대용량 데이터)",
     "reason": "수천만 행 이상 처리 시 polars 가 메모리/속도 면에서 우수합니다."},
    {"language": "python", "from": "datetime.datetime.utcnow",
     "to": "datetime.datetime.now(timezone.utc)",
     "reason": "utcnow() 는 deprecated. 타임존 인식 객체를 권장."},
    {"language": "javascript", "from": "moment",
     "to": "dayjs 또는 date-fns",
     "reason": "moment.js 는 유지보수 모드. 가벼운 대체 라이브러리 사용 권장."},
    {"language": "javascript", "from": "lodash.isEqual",
     "to": "내장 비교/structuredClone 활용",
     "reason": "단순 비교는 내장 구현으로 의존성을 줄일 수 있습니다."},
]


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _finding(
    type_key: str,
    *,
    rule_id: str,
    message: str,
    severity: str = "info",
    source: str = "rule",
    line_no: int | None = None,
    col_no: int | None = None,
    suggestion: str | None = None,
    snippet: str | None = None,
) -> dict[str, Any]:
    return {
        "type_key": type_key,
        "source": source,
        "severity": severity,
        "rule_id": rule_id,
        "line_no": line_no,
        "col_no": col_no,
        "message": message,
        "suggestion": suggestion,
        "snippet": snippet,
    }


def _iter_lines(code: str) -> Iterable[tuple[int, str]]:
    for i, raw in enumerate(code.splitlines(), start=1):
        yield i, raw


# ---------------------------------------------------------------------------
# 1) 문법 오류 (Python 은 ast 로, 다른 언어는 괄호/따옴표 균형)
# ---------------------------------------------------------------------------
def _check_syntax(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if language == "python":
        try:
            ast.parse(code)
        except SyntaxError as exc:
            out.append(_finding(
                "syntax_error",
                rule_id="PY-SYN-001",
                severity="error",
                line_no=exc.lineno,
                col_no=exc.offset,
                message=f"Python SyntaxError: {exc.msg}",
                snippet=(exc.text or "").rstrip(),
            ))
        return out

    # 비-Python: 괄호/대괄호/중괄호 균형만 빠르게 검사
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    in_str: str | None = None
    line_no = 1
    for ch in code:
        if ch == "\n":
            line_no += 1
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            continue
        if ch in pairs:
            stack.append((ch, line_no))
        elif ch in closing:
            if not stack or stack[-1][0] != closing[ch]:
                out.append(_finding(
                    "syntax_error",
                    rule_id="GEN-SYN-001",
                    severity="error",
                    line_no=line_no,
                    message=f"닫는 기호 '{ch}' 가 짝이 맞지 않습니다.",
                ))
                return out
            stack.pop()
    if stack:
        ch, ln = stack[-1]
        out.append(_finding(
            "syntax_error",
            rule_id="GEN-SYN-002",
            severity="error",
            line_no=ln,
            message=f"열린 기호 '{ch}' 가 닫히지 않았습니다.",
        ))
    return out


# ---------------------------------------------------------------------------
# 2) 오탈자
# ---------------------------------------------------------------------------
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _check_typos(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for ln, text in _iter_lines(code):
        for m in _IDENT_RE.finditer(text):
            tok = m.group(0)
            low = tok.lower()
            if low in COMMON_TYPOS and (ln, low) not in seen:
                seen.add((ln, low))
                out.append(_finding(
                    "typo",
                    rule_id="GEN-TYPO-001",
                    severity="warn",
                    line_no=ln,
                    col_no=m.start() + 1,
                    message=f"오탈자로 보입니다: '{tok}' → '{COMMON_TYPOS[low]}'",
                    suggestion=COMMON_TYPOS[low],
                    snippet=text.strip()[:240],
                ))
    return out


# ---------------------------------------------------------------------------
# 3) 불필요한 코드 (미사용 import / 의미 없는 pass / 중복 빈 줄)
# ---------------------------------------------------------------------------
def _check_dead_code_python(code: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return out

    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used_names.add(base.id)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                if local == "*":
                    continue
                if local not in used_names:
                    out.append(_finding(
                        "dead_code",
                        rule_id="PY-DEAD-001",
                        severity="warn",
                        line_no=getattr(node, "lineno", None),
                        message=f"미사용 import: '{local}'",
                        suggestion=f"'{local}' 가 실제로 쓰이지 않으면 제거하세요.",
                    ))
    return out


def _check_dead_code(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if language == "python":
        out.extend(_check_dead_code_python(code))
    # 모든 언어 공통 - 연속된 빈 줄 3개 이상
    blank = 0
    for ln, text in _iter_lines(code):
        if text.strip() == "":
            blank += 1
            if blank == 3:
                out.append(_finding(
                    "dead_code",
                    rule_id="GEN-DEAD-002",
                    severity="info",
                    line_no=ln,
                    message="연속된 빈 줄이 3개 이상입니다. 가독성을 위해 정리를 권장합니다.",
                ))
        else:
            blank = 0
    return out


# ---------------------------------------------------------------------------
# 4) 반복문 개선
# ---------------------------------------------------------------------------
_RE_RANGE_LEN = re.compile(r"\bfor\s+\w+\s+in\s+range\s*\(\s*len\s*\(")
_RE_WHILE_TRUE_BREAK = re.compile(r"\bwhile\s+(true|True|1)\s*:")
_RE_NESTED_FOR = re.compile(r"^\s{4,}for\s+", re.MULTILINE)
_RE_JS_FOR_OLD = re.compile(r"\bfor\s*\(\s*var\s+\w+\s*=\s*0\s*;\s*\w+\s*<\s*\w+\.length")


def _check_loop(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln, text in _iter_lines(code):
        if _RE_RANGE_LEN.search(text):
            out.append(_finding(
                "loop",
                rule_id="PY-LOOP-001",
                severity="info",
                line_no=ln,
                message="range(len(x)) 패턴은 enumerate(x) 로 단순화하세요.",
                suggestion="for i, item in enumerate(x):",
                snippet=text.strip()[:240],
            ))
        if _RE_WHILE_TRUE_BREAK.search(text):
            out.append(_finding(
                "loop",
                rule_id="GEN-LOOP-002",
                severity="info",
                line_no=ln,
                message="while True / while(1) 루프는 명시적인 종료 조건으로 바꾸는 것이 안전합니다.",
                snippet=text.strip()[:240],
            ))
        if language in {"javascript", "typescript"} and _RE_JS_FOR_OLD.search(text):
            out.append(_finding(
                "loop",
                rule_id="JS-LOOP-001",
                severity="info",
                line_no=ln,
                message="고전적 for(var i=0; i<arr.length; i++) 패턴은 for...of / forEach / map 으로 대체하세요.",
                suggestion="for (const item of arr) { ... }",
                snippet=text.strip()[:240],
            ))
    # 단순 nested-for 검출 (들여쓰기 4 이상의 for)
    nested = list(_RE_NESTED_FOR.finditer(code))
    if len(nested) >= 2:
        out.append(_finding(
            "algorithm",
            rule_id="GEN-ALGO-001",
            severity="info",
            line_no=code[: nested[0].start()].count("\n") + 1,
            message="중첩된 반복문이 감지되었습니다. O(n²) 이상의 복잡도일 수 있어 해시/사전 사용을 검토하세요.",
        ))
    return out


# ---------------------------------------------------------------------------
# 5) 메모리 사용량
# ---------------------------------------------------------------------------
_RE_READ_ALL = re.compile(r"\.read\s*\(\s*\)")
_RE_LIST_TO_SUM = re.compile(r"\bsum\s*\(\s*\[")
_RE_LIST_TO_ANY = re.compile(r"\b(any|all)\s*\(\s*\[")


def _check_memory(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln, text in _iter_lines(code):
        if _RE_READ_ALL.search(text):
            out.append(_finding(
                "memory",
                rule_id="GEN-MEM-001",
                severity="info",
                line_no=ln,
                message="파일을 한 번에 .read() 하고 있습니다. 큰 파일은 라인 단위/스트림으로 처리하세요.",
                suggestion="for line in f: ...",
                snippet=text.strip()[:240],
            ))
        if language == "python":
            if _RE_LIST_TO_SUM.search(text):
                out.append(_finding(
                    "memory",
                    rule_id="PY-MEM-001",
                    severity="info",
                    line_no=ln,
                    message="sum([...]) 형태는 임시 리스트를 만듭니다. 제너레이터식을 사용하세요.",
                    suggestion="sum(x for x in ...)",
                    snippet=text.strip()[:240],
                ))
            if _RE_LIST_TO_ANY.search(text):
                out.append(_finding(
                    "memory",
                    rule_id="PY-MEM-002",
                    severity="info",
                    line_no=ln,
                    message="any([...]) / all([...]) 는 제너레이터를 쓰면 단락 평가의 이점을 살릴 수 있습니다.",
                    snippet=text.strip()[:240],
                ))
    return out


# ---------------------------------------------------------------------------
# 6) 라이브러리 대체
# ---------------------------------------------------------------------------
def _check_library(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in LIBRARY_REPLACEMENTS:
        if entry["language"] != language:
            continue
        needle = entry["from"]
        if needle in code:
            ln = next(
                (i for i, t in _iter_lines(code) if needle in t),
                None,
            )
            out.append(_finding(
                "library",
                rule_id=f"LIB-{language.upper()}-{needle.replace('.', '-').upper()}",
                severity="info",
                line_no=ln,
                message=f"'{needle}' 사용 감지 — '{entry['to']}' 로 교체를 검토하세요.",
                suggestion=entry["to"],
                snippet=entry["reason"],
            ))
    return out


# ---------------------------------------------------------------------------
# 7) 알고리즘 개선 (단순 휴리스틱: in list 검색 + nested loop)
# ---------------------------------------------------------------------------
_RE_IN_LIST = re.compile(r"\bin\s+\[[^\]]{0,200}\]")


def _check_algorithm(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln, text in _iter_lines(code):
        if _RE_IN_LIST.search(text):
            out.append(_finding(
                "algorithm",
                rule_id="GEN-ALGO-002",
                severity="info",
                line_no=ln,
                message="리터럴 리스트를 in 검색에 쓰고 있습니다. set 으로 바꾸면 O(1) 검색이 가능합니다.",
                suggestion="VALUES = {'a', 'b', 'c'}; if x in VALUES: ...",
                snippet=text.strip()[:240],
            ))
    return out


# ---------------------------------------------------------------------------
# 8) 가독성
# ---------------------------------------------------------------------------
_MAX_LINE = 120
_RE_MAGIC_NUMBER = re.compile(r"(?<![A-Za-z0-9_])(\d{3,})(?![A-Za-z0-9_])")


def _check_readability(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln, text in _iter_lines(code):
        # 주석 / 문자열 라인은 magic number 체크 제외
        stripped = text.strip()
        if len(text.rstrip()) > _MAX_LINE:
            out.append(_finding(
                "readability",
                rule_id="GEN-READ-001",
                severity="info",
                line_no=ln,
                message=f"라인 길이가 {_MAX_LINE} 자를 초과합니다 ({len(text)} 자).",
                snippet=text[:200],
            ))
        if not stripped.startswith(("#", "//", "/*", "*")) and _RE_MAGIC_NUMBER.search(stripped):
            out.append(_finding(
                "readability",
                rule_id="GEN-READ-002",
                severity="info",
                line_no=ln,
                message="숫자 리터럴이 직접 등장합니다. 의미 있는 상수로 추출하면 가독성이 좋아집니다.",
                snippet=stripped[:240],
            ))
    return out


# ---------------------------------------------------------------------------
# 9) 실행 속도
# ---------------------------------------------------------------------------
_RE_STR_CONCAT_LOOP = re.compile(r"^\s+\w+\s*\+\=\s*['\"]")
_RE_LIST_CONCAT_LOOP = re.compile(r"^\s+\w+\s*\=\s*\w+\s*\+\s*\[")
_RE_REPEATED_LEN = re.compile(r"\blen\s*\(\s*\w+\s*\)\s*[><=!]+\s*len\s*\(")


def _check_speed(code: str, language: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    in_loop = False
    indent = 0
    for ln, text in _iter_lines(code):
        if re.match(r"^\s*(for|while)\b", text):
            in_loop = True
            indent = len(text) - len(text.lstrip())
            continue
        if in_loop and text.strip() and (len(text) - len(text.lstrip())) <= indent:
            in_loop = False
        if in_loop:
            if _RE_STR_CONCAT_LOOP.search(text):
                out.append(_finding(
                    "speed",
                    rule_id="GEN-SPD-001",
                    severity="warn",
                    line_no=ln,
                    message="루프 안의 문자열 += 누적은 느립니다. ''.join(parts) 또는 io.StringIO 를 사용하세요.",
                    snippet=text.strip()[:240],
                ))
            if _RE_LIST_CONCAT_LOOP.search(text):
                out.append(_finding(
                    "speed",
                    rule_id="GEN-SPD-002",
                    severity="warn",
                    line_no=ln,
                    message="루프 안의 리스트 + [..] 패턴은 매번 새 리스트를 만듭니다. .append() / .extend() 를 사용하세요.",
                    snippet=text.strip()[:240],
                ))
        if _RE_REPEATED_LEN.search(text):
            out.append(_finding(
                "speed",
                rule_id="GEN-SPD-003",
                severity="info",
                line_no=ln,
                message="동일 컬렉션의 len() 을 반복 호출합니다. 변수에 캐싱하세요.",
                snippet=text.strip()[:240],
            ))
    return out


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def analyze(code: str, language: str | None) -> dict[str, Any]:
    """규칙 기반 정적 분석. (사진 흐름의 '정적 분석' 박스)

    Returns
    -------
    {
        "language": "python",
        "lines": 42,
        "findings": [ ... finding dict ... ],
        "summary": { type_key: count, ... },
        "rule_count": int,
    }
    """
    lang = (language or "plain").lower()
    findings: list[dict[str, Any]] = []
    if not code:
        return {"language": lang, "lines": 0, "findings": [],
                "summary": {}, "rule_count": 0}

    findings.extend(_check_syntax(code, lang))
    # 문법 오류가 있어도 나머지 분석은 best-effort 로 계속한다.
    findings.extend(_check_typos(code, lang))
    findings.extend(_check_dead_code(code, lang))
    findings.extend(_check_loop(code, lang))
    findings.extend(_check_memory(code, lang))
    findings.extend(_check_library(code, lang))
    findings.extend(_check_algorithm(code, lang))
    findings.extend(_check_readability(code, lang))
    findings.extend(_check_speed(code, lang))

    summary: dict[str, int] = {k: 0 for k in OPTIMIZATION_TYPE_KEYS}
    for f in findings:
        summary[f["type_key"]] = summary.get(f["type_key"], 0) + 1

    return {
        "language": lang,
        "lines": code.count("\n") + 1,
        "findings": findings,
        "summary": summary,
        "rule_count": len(findings),
    }


def findings_to_prompt_hint(findings: list[dict[str, Any]], *, max_items: int = 30) -> str:
    """분석 결과를 LLM 프롬프트에 끼워넣을 한국어 힌트 텍스트로 변환."""
    if not findings:
        return "(규칙 기반 분석에서 특별한 문제를 찾지 못함)"
    lines: list[str] = []
    for i, f in enumerate(findings[:max_items], start=1):
        loc = f"L{f['line_no']}" if f.get("line_no") else "-"
        lines.append(
            f"{i}. [{f['type_key']}] ({loc}, {f.get('rule_id') or '-'}) {f['message']}"
            + (f"  → {f['suggestion']}" if f.get("suggestion") else "")
        )
    if len(findings) > max_items:
        lines.append(f"... 외 {len(findings) - max_items} 건")
    return "\n".join(lines)


def compare(before: str, after: str,
            applied_types: Iterable[str] | None = None) -> dict[str, Any]:
    """결과 비교 (사진 흐름의 '결과 비교' 박스).

    - 라인/문자 수 변화
    - 동일 여부
    - 적용된 최적화 유형 카운트
    """
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    same = before.strip() == after.strip()
    applied = list(applied_types or [])
    return {
        "identical": same,
        "before_lines": len(before_lines),
        "after_lines": len(after_lines),
        "line_delta": len(after_lines) - len(before_lines),
        "before_chars": len(before),
        "after_chars": len(after),
        "char_delta": len(after) - len(before),
        "applied_types": applied,
        "applied_count": len(applied),
    }
