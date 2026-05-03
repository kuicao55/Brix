"""Safe math expression evaluator using ast."""

from __future__ import annotations

import ast
import operator

from capability.base import Tool

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


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node with only arithmetic operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
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
