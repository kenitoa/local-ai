from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
}
DOCUMENT_NAMES = {"README", "README.md", "README.txt"}
DEPENDENCY_NAMES = {"package.json", "pyproject.toml", "requirements.txt", "pom.xml", "go.mod", "Cargo.toml"}


@dataclass(frozen=True)
class CodeChunk:
    content: str
    metadata: dict[str, object]


class CodeChunker:
    def chunk_file(self, project_id: str, file_path: str, content: str) -> list[CodeChunk]:
        language = detect_language(file_path)
        if is_dependency_file(file_path):
            return [self._single_chunk(project_id, file_path, language, content, "dependency", Path(file_path).name)]

        if is_document_file(file_path):
            return self._line_blocks(project_id, file_path, language, content, "document")

        if language == "python":
            chunks = self._python_symbols(project_id, file_path, content)
            if chunks:
                return chunks

        return self._line_blocks(project_id, file_path, language, content, "code_block")

    def _python_symbols(self, project_id: str, file_path: str, content: str) -> list[CodeChunk]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        lines = content.splitlines()
        chunks: list[CodeChunk] = []

        import_lines = [
            index
            for index, line in enumerate(lines, start=1)
            if line.startswith("import ") or line.startswith("from ")
        ]
        if import_lines:
            chunks.append(
                self._chunk_from_lines(
                    project_id,
                    file_path,
                    "python",
                    lines,
                    min(import_lines),
                    max(import_lines),
                    "imports",
                    "imports",
                )
            )

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                line_start = node.lineno
                line_end = getattr(node, "end_lineno", node.lineno)
                chunk_type = "class" if isinstance(node, ast.ClassDef) else "function"
                call_names = sorted(call_name(call) for call in ast.walk(node) if isinstance(call, ast.Call))
                call_names = [name for name in call_names if name]
                chunks.append(
                    self._chunk_from_lines(
                        project_id,
                        file_path,
                        "python",
                        lines,
                        line_start,
                        line_end,
                        chunk_type,
                        node.name,
                        calls=call_names,
                    )
                )

        if not chunks:
            return []

        chunks.insert(
            0,
            self._single_chunk(project_id, file_path, "python", content[:2000], "file_summary", Path(file_path).name),
        )
        return chunks

    def _line_blocks(
        self,
        project_id: str,
        file_path: str,
        language: str,
        content: str,
        chunk_type: str,
        max_lines: int = 80,
        overlap: int = 12,
    ) -> list[CodeChunk]:
        lines = content.splitlines()
        if not lines:
            return [self._single_chunk(project_id, file_path, language, "", chunk_type, Path(file_path).name)]

        chunks: list[CodeChunk] = []
        cursor = 0
        while cursor < len(lines):
            start = cursor + 1
            end = min(cursor + max_lines, len(lines))
            symbol = f"{Path(file_path).name}:{start}-{end}"
            chunks.append(
                self._chunk_from_lines(
                    project_id,
                    file_path,
                    language,
                    lines,
                    start,
                    end,
                    chunk_type,
                    symbol,
                )
            )
            if end == len(lines):
                break
            cursor = max(end - overlap, cursor + 1)
        return chunks

    def _single_chunk(
        self,
        project_id: str,
        file_path: str,
        language: str,
        content: str,
        chunk_type: str,
        symbol: str,
    ) -> CodeChunk:
        lines = content.splitlines()
        return self._make_chunk(
            project_id=project_id,
            file_path=file_path,
            language=language,
            content=content,
            chunk_type=chunk_type,
            symbol=symbol,
            line_start=1,
            line_end=max(len(lines), 1),
        )

    def _chunk_from_lines(
        self,
        project_id: str,
        file_path: str,
        language: str,
        lines: list[str],
        line_start: int,
        line_end: int,
        chunk_type: str,
        symbol: str,
        calls: list[str] | None = None,
    ) -> CodeChunk:
        content = "\n".join(lines[line_start - 1 : line_end])
        return self._make_chunk(
            project_id=project_id,
            file_path=file_path,
            language=language,
            content=content,
            chunk_type=chunk_type,
            symbol=symbol,
            line_start=line_start,
            line_end=line_end,
            calls=calls or [],
        )

    def _make_chunk(
        self,
        project_id: str,
        file_path: str,
        language: str,
        content: str,
        chunk_type: str,
        symbol: str,
        line_start: int,
        line_end: int,
        calls: list[str] | None = None,
    ) -> CodeChunk:
        digest_source = json.dumps(
            {
                "project_id": project_id,
                "file_path": file_path,
                "symbol": symbol,
                "line_start": line_start,
                "line_end": line_end,
                "content": content,
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        return CodeChunk(
            content=content,
            metadata={
                "project_id": project_id,
                "language": language,
                "file_path": file_path,
                "symbol": symbol,
                "chunk_type": chunk_type,
                "hash": f"sha256:{digest}",
                "line_start": line_start,
                "line_end": line_end,
                "calls": calls or extract_call_names(content, language),
                "imports": extract_import_names(content, language),
            },
        )


def detect_language(file_path: str) -> str:
    path = Path(file_path)
    return CODE_EXTENSIONS.get(path.suffix.lower(), "text")


def is_dependency_file(file_path: str) -> bool:
    return Path(file_path).name in DEPENDENCY_NAMES


def is_document_file(file_path: str) -> bool:
    return Path(file_path).name in DOCUMENT_NAMES or Path(file_path).suffix.lower() in {".md", ".rst", ".txt"}


def extract_call_names(content: str, language: str) -> list[str]:
    if language != "python":
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    names = sorted(call_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call))
    return [name for name in names if name]


def extract_import_names(content: str, language: str) -> list[str]:
    if language != "python":
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return sorted(set(names))


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = dotted_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""
