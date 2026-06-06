from mcp.server.fastmcp import FastMCP

from app.schemas.evidence import FactRequest
from app.tools.local_source import lookup_fact

mcp = FastMCP("source-mcp-server", host="0.0.0.0", port=8103)


@mcp.tool()
async def lookup_fact_tool(request: dict) -> dict:
    """Look up a generic entity fact from seed data, Wikidata, or Wikipedia."""

    parsed = FactRequest.model_validate(request)
    return (await lookup_fact(parsed)).model_dump()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
