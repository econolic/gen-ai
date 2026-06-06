from mcp.server.fastmcp import FastMCP

from app.schemas.dsl import DSLPlan
from app.tools.local_calc import execute_formula_dsl, haversine_km, validate_formula_expression

mcp = FastMCP("calc-mcp-server", host="0.0.0.0", port=8102)


@mcp.tool()
def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two coordinate pairs in kilometers."""

    return round(haversine_km(lat1, lon1, lat2, lon2), 3)


@mcp.tool()
def validate_formula_dsl(expression: str) -> dict:
    """Validate that a formula DSL expression only uses safe whitelisted AST nodes."""

    validate_formula_expression(expression)
    return {"valid": True}


@mcp.tool()
def execute_formula_dsl_tool(rows: list[dict], dsl: dict) -> list:
    """Execute a validated formula DSL over rows."""

    parsed = DSLPlan.model_validate(dsl)
    return execute_formula_dsl(rows, parsed)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
