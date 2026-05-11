from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParserResult:
    backend: str
    ok: bool
    language: str
    error: str = ""


class SourceParser:
    def parse(self, code: str, language: str) -> ParserResult:
        normalized = language.lower()
        tree_sitter = self._try_tree_sitter(code, normalized)
        if tree_sitter.ok:
            return tree_sitter
        if normalized == "python":
            return self._parse_python_ast(code)
        return tree_sitter

    def _try_tree_sitter(self, code: str, language: str) -> ParserResult:
        try:
            from tree_sitter_language_pack import get_parser

            parser = get_parser(language)
            tree = parser.parse(code.encode("utf-8"))
            return ParserResult(
                backend="tree-sitter",
                ok=not tree.root_node.has_error,
                language=language,
                error="tree-sitter parse error" if tree.root_node.has_error else "",
            )
        except Exception as exc:
            return ParserResult(backend="tree-sitter-unavailable", ok=False, language=language, error=str(exc))

    def _parse_python_ast(self, code: str) -> ParserResult:
        try:
            import ast

            ast.parse(code)
        except SyntaxError as exc:
            return ParserResult(backend="python-ast", ok=False, language="python", error=exc.msg)
        return ParserResult(backend="python-ast", ok=True, language="python")
