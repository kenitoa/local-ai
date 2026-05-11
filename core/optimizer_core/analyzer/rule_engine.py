from __future__ import annotations

import ast

from core.optimizer_core.analyzer.models import CodeAnalysis, FunctionInfo, OptimizationOpportunity


class AnalysisRuleEngine:
    def detect(self, tree: ast.AST, analysis: CodeAnalysis) -> list[OptimizationOpportunity]:
        opportunities: list[OptimizationOpportunity] = []
        functions_by_line = {function.line_start: function for function in analysis.functions}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function = functions_by_line.get(node.lineno)
                if function:
                    opportunities.extend(detect_membership_optimization(function, node))
                    opportunities.extend(detect_local_binding_opportunity(function))
                    opportunities.extend(detect_memoization_opportunity(function))
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
                if len(node.targets) != 1 or not same_target(node.targets[0], node.value.left):
                    continue
                opportunities.append(
                    OptimizationOpportunity(
                        rule="AUGMENTED_ASSIGNMENT",
                        reason="x = x + y 형태는 같은 대상일 때 x += y로 줄일 수 있습니다.",
                        risk="low",
                        target_line=node.lineno,
                        category="rewrite",
                        confidence=0.82,
                    )
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                opportunities.append(
                    OptimizationOpportunity(
                        rule="DYNAMIC_EXECUTION_BLOCKS_OPTIMIZATION",
                        reason=f"{node.func.id} 호출은 안전한 정적 최적화를 막습니다.",
                        risk="high",
                        target_line=node.lineno,
                        category="safety",
                        confidence=0.9,
                    )
                )
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                opportunities.append(
                    OptimizationOpportunity(
                        rule="BARE_EXCEPT_HIDES_FAILURES",
                        reason="bare except는 성능/정확성 실패를 숨겨 검증을 어렵게 만듭니다.",
                        risk="medium",
                        target_line=node.lineno,
                        category="correctness",
                        confidence=0.86,
                    )
                )
        return dedupe_opportunities(opportunities)


def detect_membership_optimization(
    function: FunctionInfo,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[OptimizationOpportunity]:
    opportunities: list[OptimizationOpportunity] = []
    for loop in [node for node in ast.walk(function_node) if isinstance(node, (ast.For, ast.AsyncFor, ast.While))]:
        for expr in ast.walk(loop):
            if not isinstance(expr, ast.Compare) or len(expr.ops) != 1 or len(expr.comparators) != 1:
                continue
            if not isinstance(expr.ops[0], (ast.In, ast.NotIn)):
                continue
            comparator = expr.comparators[0]
            if isinstance(comparator, (ast.List, ast.Tuple)):
                opportunities.append(
                    OptimizationOpportunity(
                        rule="LIST_MEMBERSHIP_TO_SET",
                        reason="반복문 안의 list/tuple membership 조회는 set 변환으로 유리할 수 있습니다.",
                        risk="medium",
                        target_line=expr.lineno,
                        symbol=function.name,
                        confidence=0.82,
                    )
                )
    return opportunities


def detect_local_binding_opportunity(function: FunctionInfo) -> list[OptimizationOpportunity]:
    repeated = [call for call in set(function.calls) if "." in call and function.calls.count(call) >= 3]
    return [
        OptimizationOpportunity(
            rule="REPEATED_ATTRIBUTE_LOOKUP_LOCAL_BINDING",
            reason=f"{call} 반복 호출은 지역 변수 바인딩으로 조회 비용을 줄일 수 있습니다.",
            risk="low",
            target_line=function.line_start,
            symbol=function.name,
            confidence=0.55,
        )
        for call in sorted(repeated)
    ]


def detect_memoization_opportunity(function: FunctionInfo) -> list[OptimizationOpportunity]:
    if function.loops == 0 or len(function.calls) < 5:
        return []
    return [
        OptimizationOpportunity(
            rule="REPEATED_PURE_CALL_MEMOIZATION",
            reason="반복문 안의 반복 호출은 순수 함수라면 memoization 후보입니다.",
            risk="medium",
            target_line=function.line_start,
            symbol=function.name,
            confidence=0.45,
        )
    ]


def dedupe_opportunities(items: list[OptimizationOpportunity]) -> list[OptimizationOpportunity]:
    seen: set[tuple[str, int, str]] = set()
    result: list[OptimizationOpportunity] = []
    for item in items:
        key = (item.rule, item.target_line, item.symbol)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def same_target(left: ast.AST, right: ast.AST) -> bool:
    if isinstance(left, ast.Name) and isinstance(right, ast.Name):
        return left.id == right.id
    if isinstance(left, ast.Attribute) and isinstance(right, ast.Attribute):
        return left.attr == right.attr and same_target(left.value, right.value)
    if isinstance(left, ast.Subscript) and isinstance(right, ast.Subscript):
        return ast.dump(left.slice) == ast.dump(right.slice) and same_target(left.value, right.value)
    return False
