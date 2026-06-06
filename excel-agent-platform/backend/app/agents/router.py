"""Task routing — strategy-based pattern matching for route decisions.

Adding a new routing rule requires only appending a ``RouteStrategy`` to ``ROUTE_STRATEGIES``.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.task_plan import RouteName, RouteDecision
from app.schemas.workbook import WorkbookProfile


@dataclass(frozen=True)
class RouteStrategy:
    """A single routing rule: predicate → route decision."""

    name: str
    route: RouteName
    reason: str
    confidence: float
    predicate: Callable[[str, WorkbookProfile, str, set[str]], bool]


def _has_operation_columns(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    return {"a", "b", "operation"}.issubset(columns) and column in {"value", "result", "результат"}


def _is_distance_task(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    return any(word in text for word in ["відстан", "distance", "расстоя"])


def _is_hybrid_task(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    asks_external_fact = any(word in text for word in ["population", "населен", "популяц"])
    asks_calculation = any(word in text for word in ["per capita", "на душу", "div", "/", "рассчитай"])
    return asks_external_fact and asks_calculation


def _is_height_task(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    return any(word in text for word in ["висот", "height", "elevation", "метр"]) or column in {
        "height",
        "elevation",
    }


def _is_external_lookup_task(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    return any(
        word in text
        for word in ["population", "населен", "популяц", "ceo", "chief executive", "директор", "founded"]
    ) or column in {"population", "ceo", "founded", "date"}


def _is_table_calc_task(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    return any(
        operator in text
        for operator in [
            "+",
            "-",
            "*",
            "/",
            "sum",
            "mean",
            "margin",
            "марж",
            "частк",
            "дол",
            "операц",
            "operation",
            "додав",
            "минус",
            "віднім",
            "множ",
            "ділен",
        ]
    )


def _is_empty_workbook(text: str, profile: WorkbookProfile, column: str, columns: set[str]) -> bool:
    return profile.first_sheet.row_count == 0


ROUTE_STRATEGIES: list[RouteStrategy] = [
    RouteStrategy(
        "operation_columns",
        "TABLE_CALC",
        "Rows contain operands A/B and an Operation column for deterministic calculation.",
        0.96,
        _has_operation_columns,
    ),
    RouteStrategy(
        "distance",
        "HYBRID",
        "Distance requires structured coordinates plus deterministic local calculation.",
        0.94,
        _is_distance_task,
    ),
    RouteStrategy(
        "hybrid_lookup_calc",
        "HYBRID",
        "Task combines external fact lookup with deterministic table calculation.",
        0.9,
        _is_hybrid_task,
    ),
    RouteStrategy(
        "height",
        "WEB_ENRICH",
        "Height is an external fact best resolved from structured sources first.",
        0.92,
        _is_height_task,
    ),
    RouteStrategy(
        "external_lookup",
        "WEB_ENRICH",
        "Task asks for an external lookup fact resolved from structured sources first.",
        0.88,
        _is_external_lookup_task,
    ),
    RouteStrategy(
        "table_calc",
        "TABLE_CALC",
        "Task can be calculated from table values.",
        0.86,
        _is_table_calc_task,
    ),
    RouteStrategy(
        "empty_workbook",
        "UNSUPPORTED",
        "Workbook has no data rows.",
        1.0,
        _is_empty_workbook,
    ),
]


def route_task(task_description: str, profile: WorkbookProfile, target_column: str) -> RouteDecision:
    text = task_description.lower()
    column = target_column.lower()
    columns = {column_profile.name.lower() for column_profile in profile.first_sheet.columns}

    for strategy in ROUTE_STRATEGIES:
        if strategy.predicate(text, profile, column, columns):
            return RouteDecision(
                route=strategy.route,
                reason=strategy.reason,
                confidence=strategy.confidence,
            )

    return RouteDecision(
        route="CLARIFICATION_REQUIRED",
        reason="Task does not clearly map to a supported target fact or calculation.",
        confidence=0.35,
    )
