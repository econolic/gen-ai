# 01 MCP Tools

This project keeps external actions behind typed MCP tools. The FastAPI
backend orchestrates work, while Excel IO, calculations, structured source
lookup, and search/extraction run through separate FastMCP services in Docker.

## Tool Groups

- Excel MCP:
  - `profile_workbook_tool`
  - `read_rows_tool`
  - `preview_rows_tool`
  - `write_enriched_workbook_tool`
- Calculation MCP:
  - `haversine_distance_km`
  - `validate_formula_dsl`
  - `execute_formula_dsl_tool`
- Source MCP:
  - `lookup_fact_tool`
  - live Wikidata lookup
  - Wikipedia summary fallback
  - exact cache and optional offline demo fallback
- Search MCP:
  - `serper_search_tool`
  - `search_numeric_fact_tool`
  - regex extraction first, OpenRouter JSON extraction fallback

## Source Order

Live demo mode uses:

1. exact fact cache
2. Wikidata structured records
3. Wikipedia summaries
4. Serper snippets
5. OpenRouter extraction from snippets
6. offline demo seeds only as the last fallback

`OFFLINE_DEMO_SEED_FIRST=true` intentionally changes this order for deterministic
offline development. The submission screenshots and live checks use
`OFFLINE_DEMO_SEED_FIRST=false`.

## Contract Principles

- Tools receive and return typed Pydantic-compatible payloads.
- Write tools are separated from read tools.
- Row updates include confidence, errors, and evidence metadata.
- Gateway and API errors use controlled envelopes.
- The backend normalizes MCP transport quirks, including single-row Excel
  responses returned as a plain object.

## Runtime Verification

Docker uses `MCP_STRICT_TOOLS=true` by default. In strict mode, graph execution
must use registered MCP tools; local fallback is disabled.

Verify the tool registry with:

```bash
make docker-health
```

Expected `/health/mcp` result:

- `status: ok`
- `strict: true`
- all four servers configured: `excel`, `calc`, `source`, `search`
- no missing tools
