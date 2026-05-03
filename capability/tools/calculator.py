"""Safe math expression evaluator using ast."""

from __future__ import annotations

import ast
import operator
from typing import Optional

from capability.base import Tool

_MAX_DEPTH = 20
_MAX_NODES = 100

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(
    node: ast.AST,
    depth: int = 0,
    _counter: Optional[list[int]] = None,
) -> float:
    """Recursively evaluate an AST node with only arithmetic operations.

    Includes DoS protections:
    - Maximum recursion depth (_MAX_DEPTH)
    - Maximum node count (_MAX_NODES) -- shared counter across entire tree
    - Exponent magnitude cap (abs <= 1000)
    """
    if _counter is None:
        _counter = [0]
    _counter[0] += 1

    if depth > _MAX_DEPTH:
        raise ValueError("Expression too deeply nested")
    if _counter[0] > _MAX_NODES:
        raise ValueError("Expression too complex")

    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, depth + 1, _counter)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        right = _safe_eval(node.right, depth + 1, _counter)
        if isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError("Exponent too large")
        return operator.pow(_safe_eval(node.left, depth + 1, _counter), right)
    if isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(
            _safe_eval(node.left, depth + 1, _counter),
            _safe_eval(node.right, depth + 1, _counter),
        )
    if isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_safe_eval(node.operand, depth + 1, _counter))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


class CalculatorTool(Tool):
    """Evaluate math expressions safely."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluate a mathematical expression and return the result."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression to evaluate, e.g. '2 + 3 * 4'",
                }
            },
            "required": ["expression"],
        }

    async def execute(self, **params) -> str:
        expression = params.get("expression", "")
        if not expression:
            return "Error: empty expression"
        try:
            tree = ast.parse(expression, mode="eval")
            result = _safe_eval(tree)
            return str(result)
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as exc:
            return f"Error: {exc}"
