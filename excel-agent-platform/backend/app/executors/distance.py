"""Distance DSL executor — haversine-based enrichment for capital pairs."""
from __future__ import annotations

from app.executors.common import extract_coordinates, request_key, resolve_fact_requests
from app.graph.state import ExcelAgentState
from app.schemas.dsl import DSLPlan
from app.schemas.evidence import FactRequest, fact_value_to_python
from app.schemas.run import CellUpdate
from app.services import mcp_gateway


async def execute_distance(state: ExcelAgentState, dsl: DSLPlan) -> list[CellUpdate]:
    """Execute a distance DSL operation using haversine over looked-up coordinates."""
    plan = state["plan"].model_copy(update={"target_column": dsl.target_column})
    updates: list[CellUpdate] = []
    pending_rows: list[tuple[dict, FactRequest, FactRequest]] = []
    requests: list[FactRequest] = []

    source_columns = dsl.source_columns or ["Capital_From", "Country_From", "Capital_To", "Country_To"]
    from_city_col = source_columns[0] if len(source_columns) > 0 else "Capital_From"
    from_country_col = source_columns[1] if len(source_columns) > 1 else "Country_From"
    to_city_col = source_columns[2] if len(source_columns) > 2 else "Capital_To"
    to_country_col = source_columns[3] if len(source_columns) > 3 else "Country_To"

    for row in state["rows"]:
        row_index = int(row["_row_index"])
        from_city = row.get(from_city_col)
        from_country = row.get(from_country_col)
        to_city = row.get(to_city_col)
        to_country = row.get(to_country_col)
        if not all([from_city, from_country, to_city, to_country]):
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=plan.target_column,
                    error="Missing city/country source columns",
                )
            )
            continue

        from_request = FactRequest(
            entity=str(from_city),
            attribute="coordinates",
            unit="degrees",
            context={"country": from_country},
        )
        to_request = FactRequest(
            entity=str(to_city),
            attribute="coordinates",
            unit="degrees",
            context={"country": to_country},
        )
        requests.extend([from_request, to_request])
        pending_rows.append((row, from_request, to_request))

    facts = await resolve_fact_requests(requests, mcp_gateway.lookup_fact)

    for row, from_request, to_request in pending_rows:
        row_index = int(row["_row_index"])
        from_city = row.get(from_city_col)
        to_city = row.get(to_city_col)
        from_fact = facts[request_key(from_request)]
        to_fact = facts[request_key(to_request)]

        if from_fact.error or to_fact.error:
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=plan.target_column,
                    confidence=0.0,
                    error=f"Coordinates not found for {from_city} or {to_city}",
                    evidence=[
                        *[item.model_dump() for item in from_fact.evidence],
                        *[item.model_dump() for item in to_fact.evidence],
                    ],
                )
            )
            continue

        from_coords = extract_coordinates(fact_value_to_python(from_fact.value))
        to_coords = extract_coordinates(fact_value_to_python(to_fact.value))

        if from_coords is None or to_coords is None:
            updates.append(
                CellUpdate(
                    row_index=row_index,
                    target_column=plan.target_column,
                    confidence=0.0,
                    error=f"Invalid coordinates format or not found for {from_city} or {to_city}",
                    evidence=[
                        *[item.model_dump() for item in from_fact.evidence],
                        *[item.model_dump() for item in to_fact.evidence],
                    ],
                )
            )
            continue

        distance = await mcp_gateway.haversine_distance_km(
            from_coords[0],
            from_coords[1],
            to_coords[0],
            to_coords[1],
        )
        confidence = min(from_fact.confidence, to_fact.confidence, 0.95)
        updates.append(
            CellUpdate(
                row_index=row_index,
                target_column=plan.target_column,
                value=round(distance, 1),
                confidence=confidence,
                evidence=[
                    *[item.model_dump() for item in from_fact.evidence],
                    *[item.model_dump() for item in to_fact.evidence],
                    {
                        "kind": "calculation",
                        "title": "Haversine great-circle distance",
                        "confidence": 0.95,
                        "metadata": {"unit": "km"},
                    },
                ],
            )
        )

    return updates
