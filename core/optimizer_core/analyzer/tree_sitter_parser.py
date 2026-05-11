from __future__ import annotations

from core.optimizer_core.source_parser import ParserResult, SourceParser


def parse_source(code: str, language: str) -> ParserResult:
    return SourceParser().parse(code, language)
