from __future__ import annotations

import ast

from core.optimizer_core.analyzer.dependency_graph import build_call_graph
from core.optimizer_core.analyzer.models import ClassInfo, CodeAnalysis, FunctionInfo, ImportInfo


class PythonAstAnalyzer:
    def analyze(self, code: str) -> CodeAnalysis:
        tree = ast.parse(code)
        functions = [self._function_info(node) for node in ast.walk(tree) if is_function(node)]
        classes = [self._class_info(node) for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        imports = [self._import_info(node) for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        return CodeAnalysis(
            functions=functions,
            classes=classes,
            imports=imports,
            call_graph=build_call_graph(functions),
        )

    def _function_info(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        body_nodes = list(ast.walk(node))
        calls = [call_name(item) for item in body_nodes if isinstance(item, ast.Call) and call_name(item)]
        return FunctionInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            args=[arg.arg for arg in node.args.args],
            calls=calls,
            loops=sum(isinstance(item, (ast.For, ast.AsyncFor, ast.While)) for item in body_nodes),
            branches=sum(isinstance(item, (ast.If, ast.IfExp, ast.Match)) for item in body_nodes),
            returns=sum(isinstance(item, ast.Return) for item in body_nodes),
            max_loop_depth=max_loop_depth(node),
            complexity=cyclomatic_complexity(node),
        )

    def _class_info(self, node: ast.ClassDef) -> ClassInfo:
        return ClassInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            methods=[item.name for item in node.body if is_function(item)],
        )

    def _import_info(self, node: ast.Import | ast.ImportFrom) -> ImportInfo:
        if isinstance(node, ast.Import):
            return ImportInfo(
                module="",
                names=[alias.name for alias in node.names],
                alias=", ".join(alias.asname or "" for alias in node.names).strip(", "),
                line=node.lineno,
            )
        return ImportInfo(
            module=node.module or "",
            names=[alias.name for alias in node.names],
            alias=", ".join(alias.asname or "" for alias in node.names).strip(", "),
            line=node.lineno,
        )


def is_function(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def cyclomatic_complexity(node: ast.AST) -> int:
    score = 1
    for item in ast.walk(node):
        if isinstance(item, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Match)):
            score += 1
        elif isinstance(item, ast.BoolOp):
            score += max(len(item.values) - 1, 0)
        elif isinstance(item, ast.comprehension):
            score += 1 + len(item.ifs)
    return score


def max_loop_depth(node: ast.AST) -> int:
    def visit(item: ast.AST, depth: int) -> int:
        next_depth = depth + 1 if isinstance(item, (ast.For, ast.AsyncFor, ast.While)) else depth
        child_depths = [visit(child, next_depth) for child in ast.iter_child_nodes(item)]
        return max([next_depth, *child_depths])

    return visit(node, 0)
