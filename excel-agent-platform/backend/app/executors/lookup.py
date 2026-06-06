"""Lookup DSL executor — structured source + search fallback enrichment."""
from __future__ import annotations

from app.executors.common import request_key, resolve_fact_requests
from app.graph.state import ExcelAgentState
from app.schemas.dsl import DSLPlan
from app.schemas.evidence import FactRequest, FactResult, fact_value_to_python
from app.schemas.run import CellUpdate
from app.services import mcp_gateway


async def _lookup_with_search(request: FactRequest) -> FactResult:
    fact = await mcp_gateway.lookup_fact(request)
    if fact.error:
        return await mcp_gateway.search_numeric_fact(request)
    return fact


async def execute_lookup(state: ExcelAgentState, dsl: DSLPlan) -> list[CellUpdate]:
    """Execute a generic lookup DSL operation for any entity attribute."""
    updates: list[CellUpdate] = []
    pending_rows: list[tuple[dict, FactRequest]] = []
    requests: list[FactRequest] = []
    entity_columns = dsl.entity_columns or dsl.source_columns[:2]
    attribute = dsl.attribute or "fact"

    for row in state["rows"]:
        row_index = int(row["_row_index"])
        entity_parts = [str(row.get(column) or "").strip() for column in entity_columns[:1]]
        entity = " ".join(part for part in entity_parts if part)
        if not entity:
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=dsl.target_column,
                    error=f"Missing entity source column: {', '.join(entity_columns[:1])}",
                )
            )
            continue

        context = {column: row.get(column) for column in entity_columns[1:] if row.get(column)}
        context["value_type"] = dsl.value_type
        request = FactRequest(
            entity=entity,
            attribute=attribute,
            unit=dsl.unit,
            context=context,
        )
        pending_rows.append((row, request))
        requests.append(request)

    facts = await resolve_fact_requests(requests, _lookup_with_search)

    for row, request in pending_rows:
        fact = facts[request_key(request)]
        updates.append(
            CellUpdate(
                row_index=int(row["_row_index"]),
                target_column=dsl.target_column,
                value=fact_value_to_python(fact.value),
                confidence=fact.confidence,
                error=fact.error,
                evidence=[item.model_dump() for item in fact.evidence],
            )
        )
    return updates
