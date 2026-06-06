from __future__ import annotations

import ast
import math
from typing import Any

import pandas as pd

from app.schemas.dsl import DSLPlan

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line great-circle distance in kilometers."""

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class _SafeExpressionValidator(ast.NodeVisitor):
    allowed_nodes = {
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Constant,
        ast.Call,
        ast.Name,
        ast.Load,
    }
    allowed_functions = {"abs", "round", "log", "exp", "sqrt", "col", "add", "sub", "mul", "div"}

    def visit(self, node: ast.AST) -> Any:
        if type(node) not in self.allowed_nodes:
            raise ValueError(f"Unsupported DSL node: {type(node).__name__}")
        return super().visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name) or node.func.id not in self.allowed_functions:
            raise ValueError("Only whitelisted math functions are allowed in DSL expressions")
        for arg in node.args:
            self.visit(arg)


def validate_formula_expression(expression: str) -> None:
    tree = ast.parse(expression, mode="eval")
    _SafeExpressionValidator().visit(tree)


def execute_formula_dsl(rows: list[dict[str, Any]], dsl: DSLPlan) -> list[Any]:
    """Execute a narrow formula DSL over rows using whitelisted AST only."""

    if dsl.expression is None:
        raise ValueError("Formula DSL requires expression")
    validate_formula_expression(dsl.expression)
    df = pd.DataFrame(rows)
    safe_functions = {
        "abs": abs,
        "round": round,
        "log": math.log,
        "exp": math.exp,
        "sqrt": math.sqrt,
        "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b,
        "mul": lambda a, b: a * b,
        "div": lambda a, b: a / b if b != 0 else float("nan"),
    }
    values = []
    code = compile(ast.parse(dsl.expression, mode="eval"), "<formula_dsl>", "eval")
    for _, row in df.iterrows():
        context = {column: row[column] for column in df.columns if column != "_row_index"}
        def col(name: str) -> Any:
            return context.get(name)
        eval_context = {
            "__builtins__": {},
            **safe_functions,
            "col": col,
            **context,
        }
        values.append(eval(code, eval_context))
    return values
