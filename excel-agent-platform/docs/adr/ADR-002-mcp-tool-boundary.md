# ADR-002: MCP Tool Boundary

## Status

Accepted

## Decision

Expose Excel IO, calculation, structured source lookup, and search fallback through separate MCP servers, with strict tool mode enabled in Docker.

The Docker topology uses these MCP services:

- `mcp-excel`: workbook profile/read/preview/write
- `mcp-calc`: haversine distance and safe DSL execution
- `mcp-source`: Wikidata/Wikipedia/cache/source lookup
- `mcp-search`: Serper search and typed extraction fallback

The backend accesses tools through `langchain-mcp-adapters` in
`app.services.mcp_gateway`.

## Consequences

Tool contracts stay isolated from orchestration code, `/health/mcp` verifies all
registered tools, and local fallback remains available only when
`MCP_STRICT_TOOLS=false`. In the submitted Docker flow, `MCP_STRICT_TOOLS=true`
is expected and `/health/mcp` must report `strict: true`, `status: ok`, and no
missing tools.
