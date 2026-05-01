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
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from collections.abc import Callable
from typing import Any, Iterable

# 사진의 9가지 최적화 유형 키 (mysql/init/11_optimize_engine.sql 와 1:1)
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
_RE_SORT_CALL = re.compile(r"\b(sorted\s*\(|\w+\.sort\s*\()")


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
        if language == "python" and _RE_SORT_CALL.search(text):
            out.append(_finding(
                "algorithm",
                rule_id="PY-ALGO-003",
                severity="warn",
                line_no=ln,
                message="정렬 호출은 일반적으로 O(n log n)입니다. 전체 정렬 순서가 필요하지 않다면 O(n) 대안을 검토하세요.",
                suggestion="최솟값/최댓값은 min()/max(), Top-K는 heapq.nsmallest/nlargest(), 멤버십은 set을 사용하세요.",
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


# ---------------------------------------------------------------------------
# O(n) 목표 최적화 파이프라인
# ---------------------------------------------------------------------------
def _complexity_rank(label: str) -> int:
    return {
        "O(1)": 0,
        "O(log n)": 1,
        "O(n) 이하": 2,
        "O(n)": 2,
        "O(n log n)": 3,
        "O(n^2)": 4,
        "O(n^3)": 5,
        "O(2^n)": 6,
        "unknown": 9,
    }.get(label, 9)


def _normalize_language(language: str | None) -> str:
    lang = (language or "plain").lower()
    return "python" if lang == "py" else lang


def _estimate_python_complexity(tree: ast.AST) -> dict[str, Any]:
    calls = 0
    recursive_calls = 0
    sorts = 0
    membership_linear = 0
    list_materializations = 0
    max_loop_depth = 0
    comprehension_depth_max = 0
    nested_comprehension = False
    in_loop_membership_linear = 0
    in_loop_index_calls = 0
    in_loop_str_concat = 0
    halving_recursion = False
    containers = {"list": 0, "dict": 0, "set": 0, "tuple": 0}
    function_stack: list[str] = []

    # 이름만 봐도 정렬/Top-K/이분탐색 빌드 등 O(n log n) 이상이 확실한 호출들
    nlogn_function_names = {"sorted"}
    nlogn_attr_names = {
        "sort", "sort_values", "sort_index", "argsort",
        "nsmallest", "nlargest", "merge",
    }

    def _is_subscript_halving(node: ast.AST) -> bool:
        # arr[:mid], arr[mid:], arr[:len(arr)//2] 같은 분할 슬라이스 패턴
        if not isinstance(node, ast.Subscript) or not isinstance(node.slice, ast.Slice):
            return False
        sl = node.slice
        for piece in (sl.lower, sl.upper):
            if piece is None:
                continue
            for child in ast.walk(piece):
                if isinstance(child, ast.FloorDiv) or (
                    isinstance(child, ast.BinOp) and isinstance(child.op, ast.FloorDiv)
                ):
                    return True
                if isinstance(child, ast.Name) and "mid" in child.id.lower():
                    return True
        return False

    def walk(node: ast.AST, loop_depth: int, comp_depth: int) -> None:
        nonlocal calls, recursive_calls, sorts, membership_linear, list_materializations
        nonlocal max_loop_depth, comprehension_depth_max, nested_comprehension
        nonlocal in_loop_membership_linear, in_loop_index_calls, in_loop_str_concat
        nonlocal halving_recursion
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_stack.append(node.name)
            for child in ast.iter_child_nodes(node):
                walk(child, loop_depth, comp_depth)
            function_stack.pop()
            return
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loop_depth += 1
            max_loop_depth = max(max_loop_depth, loop_depth)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            new_depth = comp_depth + len(node.generators)
            comprehension_depth_max = max(comprehension_depth_max, new_depth)
            if new_depth >= 2:
                nested_comprehension = True
            comp_depth = new_depth
        if isinstance(node, ast.Call):
            calls += 1
            func = node.func
            if isinstance(func, ast.Name):
                if function_stack and func.id == function_stack[-1]:
                    recursive_calls += 1
                    # arr[:mid], arr[mid:] 같은 분할이 인자로 들어오면 O(n log n) 후보
                    if any(_is_subscript_halving(a) for a in node.args):
                        halving_recursion = True
                if func.id in nlogn_function_names:
                    sorts += 1
                if func.id in {"sum", "any", "all"} and node.args and isinstance(node.args[0], ast.ListComp):
                    list_materializations += 1
            if isinstance(func, ast.Attribute):
                if func.attr in nlogn_attr_names:
                    sorts += 1
                if loop_depth >= 1 and func.attr == "index":
                    in_loop_index_calls += 1
        if isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)):
                    if isinstance(comparator, ast.List):
                        membership_linear += 1
                    if loop_depth >= 1 and isinstance(comparator, (ast.Name, ast.List)):
                        in_loop_membership_linear += 1
        if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
            if loop_depth >= 1 and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                in_loop_str_concat += 1
        if isinstance(node, ast.List):
            containers["list"] += 1
        elif isinstance(node, ast.Dict):
            containers["dict"] += 1
        elif isinstance(node, ast.Set):
            containers["set"] += 1
        elif isinstance(node, ast.Tuple):
            containers["tuple"] += 1
        for child in ast.iter_child_nodes(node):
            walk(child, loop_depth, comp_depth)

    walk(tree, 0, 0)

    # 라벨 결정 — 보수적으로(과소평가하지 않게) 우선순위를 둔다.
    if recursive_calls and not halving_recursion:
        # 분할 정복이 명확하지 않은 재귀 → 일단 O(n^2) 이상으로 본다
        label = "O(n^2)"
    elif max_loop_depth >= 2 or nested_comprehension:
        label = "O(n^2)"
    elif in_loop_membership_linear or in_loop_index_calls or in_loop_str_concat:
        # 단일 루프지만 본문이 사실상 선형 작업을 부르는 경우
        label = "O(n^2)"
    elif sorts or halving_recursion:
        label = "O(n log n)"
    else:
        label = "O(n) 이하"
    return {
        "class": label,
        "loop_depth": max_loop_depth,
        "comprehension_depth": comprehension_depth_max,
        "recursive_calls": recursive_calls,
        "halving_recursion": halving_recursion,
        "function_calls": calls,
        "sort_calls": sorts,
        "list_membership_calls": membership_linear,
        "in_loop_membership": in_loop_membership_linear,
        "in_loop_index_calls": in_loop_index_calls,
        "in_loop_str_concat": in_loop_str_concat,
        "list_materializations": list_materializations,
        "data_structures": containers,
    }


def _same_public_results(before: str, after: str) -> dict[str, Any]:
    if not (_is_safe_python_exec(before) and _is_safe_python_exec(after)):
        return {"passed": None, "method": "public_globals", "skipped": "unsafe_or_complex_code"}
    names: dict[str, Any] = {}
    try:
        exec(compile(before, "<before>", "exec"), {"__builtins__": __builtins__}, names)
        before_values = {k: v for k, v in names.items() if not k.startswith("_") and not callable(v)}
        names = {}
        exec(compile(after, "<after>", "exec"), {"__builtins__": __builtins__}, names)
        after_values = {k: v for k, v in names.items() if not k.startswith("_") and not callable(v)}
        return {"passed": before_values == after_values, "method": "public_globals"}
    except Exception as exc:  # noqa: BLE001
        return {"passed": None, "method": "public_globals", "error": str(exc)}


def _benchmark_python(code: str, rounds: int = 3) -> dict[str, Any]:
    if not _is_safe_python_exec(code):
        return {"ok": None, "skipped": "unsafe_or_complex_code", "rounds": 0}
    timings: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        try:
            exec(compile(code, "<benchmark>", "exec"), {"__builtins__": __builtins__}, {})
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "rounds": len(timings)}
        timings.append((time.perf_counter() - started) * 1000)
    return {"ok": True, "rounds": rounds, "best_ms": min(timings), "avg_ms": sum(timings) / len(timings)}


def _is_safe_python_exec(code: str) -> bool:
    allowed_calls = {"abs", "all", "any", "bool", "enumerate", "len", "max", "min", "range", "sum", "sorted"}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.With, ast.AsyncWith, ast.Try, ast.Raise, ast.Delete)):
            return False
        if isinstance(node, (ast.While, ast.AsyncFor, ast.Await, ast.Yield, ast.YieldFrom)):
            return False
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in allowed_calls:
                continue
            return False
        if isinstance(node, ast.Attribute):
            return False
    return True


def _estimate_complexity(code: str, language: str) -> dict[str, Any]:
    static = _static_complexity(code, language)
    if _complexity_resolver is not None:
        try:
            override = _complexity_resolver(code, language, static)
        except Exception as exc:  # noqa: BLE001
            override = None
            static.setdefault("resolver_error", str(exc))
        if isinstance(override, dict) and override.get("class"):
            override.setdefault("static", static)
            return override
    return static


def _static_complexity(code: str, language: str) -> dict[str, Any]:
    if language != "python":
        return {"class": "unknown", "source": "static",
                "reason": "complexity estimator currently supports Python AST"}
    try:
        result = _estimate_python_complexity(ast.parse(code))
    except SyntaxError:
        return {"class": "unknown", "source": "static", "parse_error": True}
    result.setdefault("source", "static")
    return result


# 외부에서 LLM/하이브리드 추론기를 주입할 수 있도록 한 콜러블 슬롯.
# 시그니처: (code: str, language: str, static_result: dict) -> dict | None
_complexity_resolver: Callable[[str, str, dict[str, Any]], dict[str, Any] | None] | None = None


def set_complexity_resolver(
    resolver: Callable[[str, str, dict[str, Any]], dict[str, Any] | None] | None,
) -> None:
    """피드백/학습 LLM 등 외부 추론기를 등록한다. None 이면 정적 분석만 사용."""
    global _complexity_resolver
    _complexity_resolver = resolver


def _analyze_bottlenecks(
    analysis: dict[str, Any],
    complexity: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    bottlenecks: list[dict[str, Any]] = []
    for finding in analysis.get("findings") or []:
        if finding.get("type_key") in {"algorithm", "loop", "memory", "speed", "library"}:
            bottlenecks.append({
                "type_key": finding.get("type_key"),
                "source": "finding",
                "rule_id": finding.get("rule_id"),
                "line_no": finding.get("line_no"),
                "message": finding.get("message"),
                "suggestion": finding.get("suggestion"),
            })
    metrics = {
        "algorithm": ["sort_calls", "recursive_calls", "list_membership_calls"],
        "loop": ["loop_depth"],
        "memory": ["list_materializations"],
        "speed": ["function_calls"],
    }
    for type_key, keys in metrics.items():
        for key in keys:
            value = complexity.get(key)
            if isinstance(value, int) and value > 0:
                bottlenecks.append({
                    "type_key": type_key,
                    "source": "profile",
                    "metric": key,
                    "value": value,
                    "message": f"{key}={value} 프로파일 신호가 감지되었습니다.",
                })
    if language != "python":
        bottlenecks.append({
            "type_key": "algorithm",
            "source": "capability",
            "message": "현재 자동 변환 후보 생성은 Python AST에 우선 지원됩니다.",
        })
    return bottlenecks


@dataclass(frozen=True)
class _OptimizationStrategy:
    key: str
    type_key: str
    label: str
    target_complexity: str
    generator: Callable[[str], tuple[str | None, list[str]]]


def _unparse_if_changed(code: str, transformer: ast.NodeTransformer) -> tuple[str | None, list[str]]:
    tree = ast.parse(code)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)
    notes = getattr(transformer, "notes", [])
    if not notes:
        return None, []
    new_code = ast.unparse(new_tree)
    if new_code.strip() == code.strip():
        return None, []
    return new_code, notes


class _SortedBoundaryTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.notes: list[str] = []

    def visit_Subscript(self, node: ast.Subscript):  # noqa: N802
        node = self.generic_visit(node)
        if not (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "sorted"
            and node.value.args
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, int)
        ):
            return node
        if any(keyword.arg == "key" for keyword in node.value.keywords):
            return node
        reverse = next(
            (keyword.value.value for keyword in node.value.keywords
             if keyword.arg == "reverse" and isinstance(keyword.value, ast.Constant)),
            False,
        )
        if node.slice.value == 0:
            func_name = "max" if reverse else "min"
        elif node.slice.value == -1:
            func_name = "min" if reverse else "max"
        else:
            return node
        self.notes.append("sorted(...)[0/-1]를 min()/max()로 바꿔 O(n log n)을 O(n)으로 낮췄습니다.")
        return ast.copy_location(
            ast.Call(func=ast.Name(id=func_name, ctx=ast.Load()), args=[node.value.args[0]], keywords=[]),
            node,
        )


class _RangeLenTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.notes: list[str] = []

    def visit_For(self, node: ast.For):  # noqa: N802
        node = self.generic_visit(node)
        if not (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and len(node.iter.args) == 1
            and isinstance(node.iter.args[0], ast.Call)
            and isinstance(node.iter.args[0].func, ast.Name)
            and node.iter.args[0].func.id == "len"
            and len(node.iter.args[0].args) == 1
            and isinstance(node.target, ast.Name)
            and isinstance(node.iter.args[0].args[0], ast.Name)
        ):
            return node
        seq = node.iter.args[0].args[0]
        index_name = node.target.id
        item_name = seq.id[:-1] if seq.id.endswith("s") and len(seq.id) > 1 else "item"
        item_name = item_name if item_name != index_name else f"{item_name}_item"
        index_uses = sum(1 for stmt in node.body for child in ast.walk(stmt) if isinstance(child, ast.Name) and child.id == index_name)
        subscript_uses = sum(
            1 for stmt in node.body for child in ast.walk(stmt)
            if isinstance(child, ast.Subscript)
            and isinstance(child.value, ast.Name)
            and child.value.id == seq.id
            and isinstance(child.slice, ast.Name)
            and child.slice.id == index_name
        )
        replacer = _SubscriptNameTransformer(seq.id, index_name, item_name)
        node.body = [replacer.visit(stmt) for stmt in node.body]
        if index_uses > subscript_uses:
            node.target = ast.Tuple(
                elts=[ast.Name(id=index_name, ctx=ast.Store()), ast.Name(id=item_name, ctx=ast.Store())],
                ctx=ast.Store(),
            )
            node.iter = ast.Call(func=ast.Name(id="enumerate", ctx=ast.Load()), args=[seq], keywords=[])
        else:
            node.target = ast.Name(id=item_name, ctx=ast.Store())
            node.iter = seq
        self.notes.append("range(len(seq)) 반복을 직접 순회 또는 enumerate(seq)로 바꿨습니다.")
        return node


class _SubscriptNameTransformer(ast.NodeTransformer):
    def __init__(self, seq_name: str, index_name: str, item_name: str) -> None:
        self.seq_name = seq_name
        self.index_name = index_name
        self.item_name = item_name

    def visit_Subscript(self, node: ast.Subscript):  # noqa: N802
        node = self.generic_visit(node)
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == self.seq_name
            and isinstance(node.slice, ast.Name)
            and node.slice.id == self.index_name
        ):
            return ast.copy_location(ast.Name(id=self.item_name, ctx=ast.Load()), node)
        return node


class _ListLiteralMembershipTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.notes: list[str] = []

    def visit_Compare(self, node: ast.Compare):  # noqa: N802
        node = self.generic_visit(node)
        changed = False
        comparators: list[ast.expr] = []
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)) and isinstance(comparator, ast.List):
                comparator = ast.Set(elts=comparator.elts)
                changed = True
            comparators.append(comparator)
        if changed:
            node.comparators = comparators
            self.notes.append("리터럴 리스트 membership을 set membership으로 바꿔 조회 비용을 낮췄습니다.")
        return node


class _GeneratorMaterializationTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.notes: list[str] = []

    def visit_Call(self, node: ast.Call):  # noqa: N802
        node = self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"sum", "any", "all"}
            and node.args
            and isinstance(node.args[0], ast.ListComp)
        ):
            node.args[0] = ast.GeneratorExp(elt=node.args[0].elt, generators=node.args[0].generators)
            self.notes.append("sum/any/all 내부 리스트 컴프리헨션을 제너레이터식으로 바꿔 메모리 사용을 줄였습니다.")
        return node


def _strategy_sorted_boundary(code: str) -> tuple[str | None, list[str]]:
    return _unparse_if_changed(code, _SortedBoundaryTransformer())


def _strategy_range_len(code: str) -> tuple[str | None, list[str]]:
    return _unparse_if_changed(code, _RangeLenTransformer())


def _strategy_list_membership(code: str) -> tuple[str | None, list[str]]:
    return _unparse_if_changed(code, _ListLiteralMembershipTransformer())


def _strategy_generator_materialization(code: str) -> tuple[str | None, list[str]]:
    return _unparse_if_changed(code, _GeneratorMaterializationTransformer())


# --- 추가: 중첩 상수 카운터 루프 → 산술식 ----------------------------------
# slow_sum(n): for i in range(n): for j in range(n): total += 1  같은 패턴을
# total += n * n * 1 (즉 O(1)) 로 평탄화한다.
def _name_used(name: str, nodes: Iterable[ast.AST]) -> bool:
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == name:
                return True
    return False


def _range_count_expr(call: ast.Call) -> ast.expr | None:
    """range(n) / range(a, b) / range(a, b, s) 의 길이 식을 만들어 반환."""
    if not (isinstance(call.func, ast.Name) and call.func.id == "range" and call.keywords == []):
        return None
    args = call.args
    if len(args) == 1:
        return args[0]
    if len(args) == 2:
        return ast.BinOp(left=args[1], op=ast.Sub(), right=args[0])
    if len(args) == 3:
        # max(0, (b - a + (s - sign(s))) // s) 같은 정확식 대신 보수적으로 패스
        return None
    return None


class _ConstantCounterNestTransformer(ast.NodeTransformer):
    """중첩 for 루프 안의 상수/루프변수 비의존 누적식을 곱셈 한 줄로 바꾼다."""

    def __init__(self) -> None:
        self.notes: list[str] = []

    def _try_flatten(self, node: ast.For) -> ast.AST | None:
        if not isinstance(node.target, ast.Name) or len(node.body) != 1:
            return None
        if node.orelse:
            return None
        outer_var = node.target.id
        outer_count = _range_count_expr(node.iter) if isinstance(node.iter, ast.Call) else None
        if outer_count is None:
            return None
        inner = node.body[0]
        if not isinstance(inner, ast.For) or inner.orelse:
            return None
        if not isinstance(inner.target, ast.Name) or len(inner.body) != 1:
            return None
        inner_var = inner.target.id
        inner_count = _range_count_expr(inner.iter) if isinstance(inner.iter, ast.Call) else None
        if inner_count is None:
            return None
        body_stmt = inner.body[0]
        if not (
            isinstance(body_stmt, ast.AugAssign)
            and isinstance(body_stmt.op, ast.Add)
            and isinstance(body_stmt.target, ast.Name)
        ):
            return None
        # 누적식과 range 카운트에 루프 변수(i, j)가 등장하면 안 됨
        nodes_to_check = [body_stmt.value, outer_count, inner_count]
        if _name_used(outer_var, nodes_to_check) or _name_used(inner_var, nodes_to_check):
            return None
        # outer/inner 카운트와 누적값을 곱한 식으로 치환
        product: ast.expr = ast.BinOp(left=outer_count, op=ast.Mult(), right=inner_count)
        if not (isinstance(body_stmt.value, ast.Constant) and body_stmt.value.value == 1):
            product = ast.BinOp(left=product, op=ast.Mult(), right=body_stmt.value)
        new_node = ast.copy_location(
            ast.AugAssign(target=body_stmt.target, op=ast.Add(), value=product),
            node,
        )
        self.notes.append(
            "루프 변수에 의존하지 않는 상수 누적의 중첩 for 를 산술식으로 평탄화했습니다 (O(n^2) → O(1))."
        )
        return new_node

    def visit_For(self, node: ast.For):  # noqa: N802
        node = self.generic_visit(node)
        replacement = self._try_flatten(node)
        return replacement or node


def _strategy_constant_counter_nest(code: str) -> tuple[str | None, list[str]]:
    return _unparse_if_changed(code, _ConstantCounterNestTransformer())


# --- 추가: 선형 dedup 루프 → set 보조 자료구조 ----------------------------
# `if x not in result: result.append(x)` 패턴을 set 으로 가속해 O(n^2) → O(n).
class _DedupAppendLoopTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.notes: list[str] = []
        self._seen_counter = 0

    def _next_seen_name(self, hint: str) -> str:
        self._seen_counter += 1
        suffix = "" if self._seen_counter == 1 else f"_{self._seen_counter}"
        return f"_seen_{hint}{suffix}"

    def _match(self, body_stmt: ast.stmt, item_name: str) -> str | None:
        if not isinstance(body_stmt, ast.If):
            return None
        # else 가 비어있거나 단순 pass 만 있을 때만 안전하게 변환
        if body_stmt.orelse and not all(isinstance(s, ast.Pass) for s in body_stmt.orelse):
            return None
        test = body_stmt.test
        if not (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.NotIn)
            and isinstance(test.left, ast.Name)
            and test.left.id == item_name
            and isinstance(test.comparators[0], ast.Name)
        ):
            return None
        target_name = test.comparators[0].id
        if len(body_stmt.body) != 1:
            return None
        call_stmt = body_stmt.body[0]
        if not (
            isinstance(call_stmt, ast.Expr)
            and isinstance(call_stmt.value, ast.Call)
            and isinstance(call_stmt.value.func, ast.Attribute)
            and call_stmt.value.func.attr == "append"
            and isinstance(call_stmt.value.func.value, ast.Name)
            and call_stmt.value.func.value.id == target_name
            and len(call_stmt.value.args) == 1
            and isinstance(call_stmt.value.args[0], ast.Name)
            and call_stmt.value.args[0].id == item_name
        ):
            return None
        return target_name

    def _build_replacement(
        self, *, item_name: str, target_name: str, iter_expr: ast.expr, original: ast.stmt
    ) -> list[ast.stmt]:
        seen_name = self._next_seen_name(target_name)
        seen_init = ast.Assign(
            targets=[ast.Name(id=seen_name, ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="set", ctx=ast.Load()),
                args=[ast.Name(id=target_name, ctx=ast.Load())],
                keywords=[],
            ),
        )
        new_for = ast.For(
            target=ast.Name(id=item_name, ctx=ast.Store()),
            iter=iter_expr,
            body=[
                ast.If(
                    test=ast.Compare(
                        left=ast.Name(id=item_name, ctx=ast.Load()),
                        ops=[ast.NotIn()],
                        comparators=[ast.Name(id=seen_name, ctx=ast.Load())],
                    ),
                    body=[
                        ast.Expr(value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id=seen_name, ctx=ast.Load()),
                                attr="add", ctx=ast.Load(),
                            ),
                            args=[ast.Name(id=item_name, ctx=ast.Load())], keywords=[],
                        )),
                        ast.Expr(value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id=target_name, ctx=ast.Load()),
                                attr="append", ctx=ast.Load(),
                            ),
                            args=[ast.Name(id=item_name, ctx=ast.Load())], keywords=[],
                        )),
                    ],
                    orelse=[],
                ),
            ],
            orelse=[],
        )
        ast.copy_location(seen_init, original)
        ast.copy_location(new_for, original)
        self.notes.append(
            "선형 검색 dedup 루프를 set 보조 자료구조로 변환해 멤버십 비용을 O(1)로 낮췄습니다."
        )
        return [seen_init, new_for]

    def visit_For(self, node: ast.For):  # noqa: N802
        node = self.generic_visit(node)
        if not (isinstance(node.target, ast.Name) and len(node.body) == 1):
            return node
        target_name = self._match(node.body[0], node.target.id)
        if not target_name:
            return node
        return self._build_replacement(
            item_name=node.target.id,
            target_name=target_name,
            iter_expr=node.iter,
            original=node,
        )

    def visit_While(self, node: ast.While):  # noqa: N802
        # while i < len(seq): if seq[i] not in y: y.append(seq[i]) ; i += 1
        node = self.generic_visit(node)
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Lt)
            and isinstance(test.left, ast.Name)
            and isinstance(test.comparators[0], ast.Call)
            and isinstance(test.comparators[0].func, ast.Name)
            and test.comparators[0].func.id == "len"
            and len(test.comparators[0].args) == 1
            and isinstance(test.comparators[0].args[0], ast.Name)
        ):
            return node
        index_name = test.left.id
        seq_name = test.comparators[0].args[0].id
        if len(node.body) < 2 or node.orelse:
            return node
        increment = node.body[-1]
        if not (
            isinstance(increment, ast.AugAssign)
            and isinstance(increment.target, ast.Name)
            and increment.target.id == index_name
            and isinstance(increment.op, ast.Add)
            and isinstance(increment.value, ast.Constant)
            and increment.value.value == 1
        ):
            return node
        # 본문이 단일 If 인지 확인 (마지막은 i += 1)
        if len(node.body) != 2 or not isinstance(node.body[0], ast.If):
            return node
        guard = node.body[0]
        # else 가 비어있거나 pass 만 있을 때만 변환
        if guard.orelse and not all(isinstance(s, ast.Pass) for s in guard.orelse):
            return node
        # 패턴: if seq[i] not in result: result.append(seq[i])
        def _is_seq_index(expr: ast.AST) -> bool:
            return (
                isinstance(expr, ast.Subscript)
                and isinstance(expr.value, ast.Name)
                and expr.value.id == seq_name
                and isinstance(expr.slice, ast.Name)
                and expr.slice.id == index_name
            )
        if not (
            isinstance(guard.test, ast.Compare)
            and len(guard.test.ops) == 1
            and isinstance(guard.test.ops[0], ast.NotIn)
            and _is_seq_index(guard.test.left)
            and isinstance(guard.test.comparators[0], ast.Name)
        ):
            return node
        target_name = guard.test.comparators[0].id
        if len(guard.body) != 1:
            return node
        call_stmt = guard.body[0]
        if not (
            isinstance(call_stmt, ast.Expr)
            and isinstance(call_stmt.value, ast.Call)
            and isinstance(call_stmt.value.func, ast.Attribute)
            and call_stmt.value.func.attr == "append"
            and isinstance(call_stmt.value.func.value, ast.Name)
            and call_stmt.value.func.value.id == target_name
            and len(call_stmt.value.args) == 1
            and _is_seq_index(call_stmt.value.args[0])
        ):
            return node
        item_name = f"{seq_name}_item" if seq_name != "item" else "value"
        if item_name == index_name:
            item_name = f"{item_name}_v"
        return self._build_replacement(
            item_name=item_name,
            target_name=target_name,
            iter_expr=ast.Name(id=seq_name, ctx=ast.Load()),
            original=node,
        )


def _strategy_dedup_append_loop(code: str) -> tuple[str | None, list[str]]:
    return _unparse_if_changed(code, _DedupAppendLoopTransformer())


PYTHON_OPTIMIZATION_STRATEGIES: tuple[_OptimizationStrategy, ...] = (
    _OptimizationStrategy("sorted_boundary_to_minmax", "algorithm", "정렬 경계값을 min/max로 대체", "O(n)", _strategy_sorted_boundary),
    _OptimizationStrategy("range_len_to_iteration", "loop", "인덱스 반복을 직접 순회로 대체", "O(n)", _strategy_range_len),
    _OptimizationStrategy("literal_list_membership_to_set", "algorithm", "리스트 membership을 set membership으로 대체", "O(1) lookup", _strategy_list_membership),
    _OptimizationStrategy("list_materialization_to_generator", "memory", "중간 리스트 생성을 제너레이터로 대체", "O(n) memory-light", _strategy_generator_materialization),
    _OptimizationStrategy("constant_counter_nest_to_arith", "algorithm", "상수 누적 중첩 for 를 산술식으로 평탄화", "O(1)", _strategy_constant_counter_nest),
    _OptimizationStrategy("dedup_append_loop_to_set", "algorithm", "선형 dedup 루프를 set 보조 자료구조로 변환", "O(n)", _strategy_dedup_append_loop),
)


def _available_strategies(language: str, bottlenecks: list[dict[str, Any]]) -> list[_OptimizationStrategy]:
    if language != "python":
        return []
    type_keys = {str(item.get("type_key")) for item in bottlenecks}
    return [strategy for strategy in PYTHON_OPTIMIZATION_STRATEGIES if not type_keys or strategy.type_key in type_keys]


def _similarity(before: str, after: str) -> float:
    return SequenceMatcher(None, before.strip(), after.strip()).ratio()


def _validate_candidate(before: str, after: str, language: str) -> dict[str, Any]:
    validation: dict[str, Any] = {"syntax": {"passed": True}, "equivalence": {"passed": None}, "similarity": _similarity(before, after)}
    if language == "python":
        try:
            ast.parse(after)
        except SyntaxError as exc:
            validation["syntax"] = {"passed": False, "error": exc.msg, "line_no": exc.lineno}
            return validation
        validation["equivalence"] = _same_public_results(before, after)
    return validation


def _benchmark_candidate(before: str, after: str, language: str) -> dict[str, Any]:
    if language != "python":
        return {"before": {"ok": None, "skipped": "unsupported_language"}, "after": {"ok": None, "skipped": "unsupported_language"}}
    return {"before": _benchmark_python(before), "after": _benchmark_python(after)}


def _is_benchmark_regression(benchmark: dict[str, Any]) -> bool:
    before = benchmark.get("before") or {}
    after = benchmark.get("after") or {}
    if before.get("ok") is not True or after.get("ok") is not True:
        return False
    before_best = float(before.get("best_ms") or 0)
    after_best = float(after.get("best_ms") or 0)
    return bool(before_best and after_best > before_best * 1.15)


def _candidate_acceptance(
    validation: dict[str, Any],
    complexity_before: dict[str, Any],
    complexity_after: dict[str, Any],
    benchmark: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if validation.get("syntax", {}).get("passed") is False:
        reasons.append("syntax_failed")
    if validation.get("equivalence", {}).get("passed") is False:
        reasons.append("equivalence_failed")
    if _is_benchmark_regression(benchmark):
        reasons.append("benchmark_regression")
    after_rank = _complexity_rank(str(complexity_after.get("class", "unknown")))
    before_rank = _complexity_rank(str(complexity_before.get("class", "unknown")))
    # 분류기가 같은 등급이라도 패턴 변환은 국소 개선일 수 있다.
    # 복잡도가 더 나빠진 경우에만 거부한다.
    if after_rank > before_rank:
        reasons.append("complexity_regressed")
    return not reasons, reasons


def _failure_report(language: str, complexity_before: dict[str, Any], bottlenecks: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if language != "python":
        reason = "unsupported_language_for_auto_rewrite"
    elif not candidates:
        reason = "no_matching_known_strategy"
    else:
        reason = "all_candidates_rejected"
    return {
        "reason": reason,
        "message": "모든 후보가 채택 조건을 만족하지 못했습니다.",
        "complexity_before": complexity_before,
        "bottleneck_count": len(bottlenecks),
        "candidate_count": len(candidates),
        "partial_optimizations": [item.get("suggestion") for item in bottlenecks if item.get("suggestion")],
    }


def _pipeline_steps(status: str) -> list[dict[str, str]]:
    return [{"name": step, "status": "done"} for step in [
        "source_code_ast_parse",
        "loop_recursion_call_datastructure_analysis",
        "complexity_estimation",
        "linear_or_less_gate",
        "bottleneck_detection",
        "known_pattern_match",
        "strategy_selection",
        "candidate_generation",
        "equivalence_test",
        "post_complexity_check",
        "benchmark",
        "accept_or_try_next",
        "result_or_failure_report",
    ]]


def _build_pipeline_result(
    *,
    status: str,
    optimized_code: str | None,
    failure_report: dict[str, Any] | None,
    analysis: dict[str, Any],
    complexity_before: dict[str, Any],
    complexity_after: dict[str, Any] | None,
    bottlenecks: list[dict[str, Any]] | None = None,
    selected_strategy: str | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "optimized_code": optimized_code,
        "failure_report": failure_report,
        "analysis": analysis,
        "complexity_before": complexity_before,
        "complexity_after": complexity_after,
        "bottlenecks": bottlenecks or [],
        "selected_strategy": selected_strategy,
        "candidates": candidates or [],
        "steps": _pipeline_steps(status),
    }


def optimize_pipeline(source_code: str, language: str | None = None) -> dict[str, Any]:
    """사용자 명세의 14단계 O(n) 목표 최적화 파이프라인."""
    lang = _normalize_language(language)
    analysis = analyze(source_code, lang)
    syntax_errors = [f for f in analysis["findings"] if f["type_key"] == "syntax_error"]
    if syntax_errors:
        return _build_pipeline_result(
            status="failed",
            optimized_code=None,
            failure_report={"reason": "parse_error", "message": "AST 파싱이 실패해 최적화를 진행할 수 없습니다."},
            analysis=analysis,
            complexity_before={"class": "unknown", "parse_error": True},
            complexity_after=None,
        )

    complexity_before = _estimate_complexity(source_code, lang)
    bottlenecks = _analyze_bottlenecks(analysis, complexity_before, lang)
    if _complexity_rank(str(complexity_before.get("class", "unknown"))) <= _complexity_rank("O(n)"):
        return _build_pipeline_result(
            status="ok",
            optimized_code=source_code,
            failure_report=None,
            analysis=analysis,
            complexity_before=complexity_before,
            complexity_after=complexity_before,
            bottlenecks=bottlenecks,
            selected_strategy="return_original",
            candidates=[{"strategy": "return_original", "accepted": True, "reason": "현재 복잡도가 O(n) 이하입니다."}],
        )

    candidates: list[dict[str, Any]] = []
    current_code = source_code
    current_complexity = complexity_before
    applied_strategies: list[str] = []
    for strategy in _available_strategies(lang, bottlenecks):
        try:
            candidate_code, notes = strategy.generator(current_code)
        except Exception as exc:  # noqa: BLE001
            candidates.append({"strategy": strategy.key, "type_key": strategy.type_key, "accepted": False, "rejection_reasons": ["generator_error"], "error": str(exc)})
            continue
        if not candidate_code:
            candidates.append({"strategy": strategy.key, "type_key": strategy.type_key, "accepted": False, "rejection_reasons": ["pattern_not_found"]})
            continue
        complexity_after = _estimate_complexity(candidate_code, lang)
        validation = _validate_candidate(current_code, candidate_code, lang)
        benchmark = _benchmark_candidate(current_code, candidate_code, lang)
        accepted, rejection_reasons = _candidate_acceptance(
            validation, current_complexity, complexity_after, benchmark,
        )
        candidate = {
            "strategy": strategy.key,
            "type_key": strategy.type_key,
            "label": strategy.label,
            "target_complexity": strategy.target_complexity,
            "accepted": accepted,
            "rejection_reasons": rejection_reasons,
            "notes": notes,
            "code": candidate_code,
            "complexity_after": complexity_after,
            "validation": validation,
            "benchmark": benchmark,
        }
        candidates.append(candidate)
        if accepted:
            current_code = candidate_code
            current_complexity = complexity_after
            applied_strategies.append(strategy.key)
            # O(n) 이하로 떨어지면 더 시도할 필요가 없다.
            if _complexity_rank(str(current_complexity.get("class", "unknown"))) <= _complexity_rank("O(n)"):
                break

    if applied_strategies:
        final_rank = _complexity_rank(str(current_complexity.get("class", "unknown")))
        if final_rank <= _complexity_rank("O(n)"):
            status = "ok"
            failure_report = None
        else:
            status = "partial"
            failure_report = {
                "reason": "linear_target_not_reached",
                "message": (
                    f"부분 최적화를 적용했지만 최종 복잡도는 "
                    f"{current_complexity.get('class')} 입니다. 추가 수동 리팩터링이 필요합니다."
                ),
                "complexity_before": complexity_before,
                "complexity_after": current_complexity,
                "applied_strategies": applied_strategies,
            }
        return _build_pipeline_result(
            status=status,
            optimized_code=current_code,
            failure_report=failure_report,
            analysis=analysis,
            complexity_before=complexity_before,
            complexity_after=current_complexity,
            bottlenecks=bottlenecks,
            selected_strategy="+".join(applied_strategies),
            candidates=candidates,
        )

    report = _failure_report(lang, complexity_before, bottlenecks, candidates)
    return _build_pipeline_result(
        status="partial",
        optimized_code=source_code,
        failure_report=report,
        analysis=analysis,
        complexity_before=complexity_before,
        complexity_after=complexity_before,
        bottlenecks=bottlenecks,
        candidates=candidates,
    )
