"""Group-share DSL executor — percentage share within grouped rows."""
from __future__ import annotations

from typing import Any

from app.executors.common import as_number
from app.graph.state import ExcelAgentState
from app.schemas.dsl import DSLPlan
from app.schemas.run import CellUpdate


async def execute_group_share(state: ExcelAgentState, dsl: DSLPlan) -> list[CellUpdate]:
    """Execute a group-share DSL operation (value / group_sum)."""
    source_columns = dsl.source_columns
    if not source_columns:
        return [
            CellUpdate(
                row_index=int(row["_row_index"]),
                target_column=dsl.target_column,
                error="Group share DSL requires a numeric source column.",
            )
            for row in state["rows"]
        ]

    value_column = source_columns[0]
    group_column = source_columns[1] if len(source_columns) > 1 else None
    group_totals: dict[Any, float] = {}
    for row in state["rows"]:
        key = row.get(group_column) if group_column else "__all__"
        try:
            group_totals[key] = group_totals.get(key, 0.0) + as_number(row.get(value_column))
        except ValueError:
            group_totals.setdefault(key, 0.0)

    updates: list[CellUpdate] = []
    for row in state["rows"]:
        row_index = int(row["_row_index"])
        key = row.get(group_column) if group_column else "__all__"
        total = group_totals.get(key, 0.0)
        try:
            value = as_number(row.get(value_column))
            if total == 0:
                raise ValueError("Group total is zero")
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=dsl.target_column,
                    value=round(value / total, 6),
                    confidence=0.98,
                    evidence=[
                        {
                            "kind": "calculation",
                            "title": "Group share",
                            "confidence": 0.98,
                            "metadata": {
                                "value_column": value_column,
                                "group_column": group_column,
                                "group_total": total,
                            },
                        }
                    ],
                )
            )
        except ValueError as exc:
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=dsl.target_column,
                    error=str(exc),
                )
            )
    return updates
