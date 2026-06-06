"""DSL executor registry — maps DSL types to async executor callables.

Adding a new DSL operation requires only:
1. Creating a new module in ``executors/``
2. Adding an entry to ``EXECUTOR_REGISTRY``
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.executors.distance import execute_distance
from app.executors.formula import execute_formula
from app.executors.group_share import execute_group_share
from app.executors.lookup import execute_lookup
from app.graph.state import ExcelAgentState
from app.schemas.dsl import DSLPlan
from app.schemas.run import CellUpdate

# Re-export common helpers used by tests
from app.executors.common import (  # noqa: F401
    extract_coordinates,
    request_key,
    resolve_fact_requests,
)

EXECUTOR_REGISTRY: dict[str, Callable[[ExcelAgentState, DSLPlan], Awaitable[list[CellUpdate]]]] = {
    "formula": execute_formula,
    "group_share": execute_group_share,
    "lookup": execute_lookup,
    "distance": execute_distance,
}
