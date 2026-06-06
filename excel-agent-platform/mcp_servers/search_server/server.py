from mcp.server.fastmcp import FastMCP

from app.schemas.evidence import FactRequest
from app.tools.local_search import search_numeric_fact, serper_search

mcp = FastMCP("search-mcp-server", host="0.0.0.0", port=8104)


@mcp.tool()
async def serper_search_tool(query: str, num: int = 5) -> list[dict]:
    """Search the public web with Serper and return organic results."""

    return await serper_search(query, num)


@mcp.tool()
async def search_numeric_fact_tool(request: dict) -> dict:
    """Search snippets for a numeric fact such as a height in meters."""

    parsed = FactRequest.model_validate(request)
    return (await search_numeric_fact(parsed)).model_dump()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
