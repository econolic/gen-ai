"""Formula DSL executor — safe expression evaluation and row-wise operations."""
from __future__ import annotations

from typing import Any

from app.executors.common import as_number, format_number
from app.graph.state import ExcelAgentState
from app.schemas.dsl import DSLPlan
from app.schemas.run import CellUpdate
from app.services import mcp_gateway
from app.services.operation_resolver import OperationResolution, normalize_operation_text, resolve_operations


def _execute_operation(a_value: Any, b_value: Any, operation: OperationResolution) -> int | float:
    a = as_number(a_value)
    b = as_number(b_value)
    if operation.symbol is None:
        raise ValueError(operation.reason)
    if operation.symbol == "+":
        return format_number(a + b)
    if operation.symbol == "-":
        return format_number(a - b)
    if operation.symbol == "*":
        return format_number(a * b)
    if b == 0:
        raise ValueError("Division by zero")
    return format_number(a / b)


async def _enrich_row_operation(state: ExcelAgentState) -> list[CellUpdate]:
    plan = state["plan"]
    source_columns = plan.source_columns or ["A", "B", "Operation"]
    a_column, b_column, operation_column = source_columns[:3]
    updates: list[CellUpdate] = []
    operation_resolutions = await resolve_operations(
        (row.get(operation_column) for row in state["rows"]),
        context_text=state.get("task_description"),
    )

    for row in state["rows"]:
        row_index = int(row["_row_index"])
        operation_label = normalize_operation_text(row.get(operation_column))
        operation = operation_resolutions[operation_label]
        try:
            value = _execute_operation(
                row.get(a_column),
                row.get(b_column),
                operation,
            )
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=plan.target_column,
                    value=value,
                    confidence=operation.confidence,
                    evidence=[
                        {
                            "kind": "calculation",
                            "title": "Row-wise operation from A/B/Operation",
                            "confidence": operation.confidence,
                            "metadata": {
                                "a_column": a_column,
                                "b_column": b_column,
                                "operation_column": operation_column,
                                "operation_label": row.get(operation_column),
                                "operation_symbol": operation.symbol,
                                "resolver_source": operation.source,
                                "resolver_reason": operation.reason,
                            },
                        }
                    ],
                )
            )
        except ValueError as exc:
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=plan.target_column,
                    error=f"Could not understand Operation '{row.get(operation_column)}': {exc}",
                    evidence=[
                        {
                            "kind": "calculation",
                            "title": "Unresolved row-wise operation",
                            "confidence": operation.confidence,
                            "metadata": {
                                "operation_label": row.get(operation_column),
                                "resolver_source": operation.source,
                                "resolver_reason": operation.reason,
                            },
                        }
                    ],
                )
            )

    return updates


async def execute_formula(state: ExcelAgentState, dsl: DSLPlan) -> list[CellUpdate]:
    """Execute a formula DSL operation — either a row-wise A/B/Op pattern or a safe expression."""
    if dsl.expression == "apply_operation(A, B, Operation)":
        return await _enrich_row_operation(state)

    try:
        values = await mcp_gateway.execute_formula_dsl(state["rows"], dsl)
    except Exception as exc:
        return [
            CellUpdate(
                row_index=int(row["_row_index"]),
                target_column=dsl.target_column,
                error=f"Formula DSL failed: {exc}",
            )
            for row in state["rows"]
        ]

    return [
        CellUpdate(
            row_index=int(row["_row_index"]),
            target_column=dsl.target_column,
            value=value,
            confidence=0.98,
            evidence=[
                {
                    "kind": "calculation",
                    "title": "Formula DSL execution",
                    "confidence": 0.98,
                    "metadata": {
                        "expression": dsl.expression,
                        "source_columns": dsl.source_columns,
                    },
                }
            ],
        )
        for row, value in zip(state["rows"], values, strict=False)
    ]
