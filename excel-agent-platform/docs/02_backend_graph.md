# 02 Backend Graph

## LangGraph Flow

```text
profile_workbook
-> plan_task
-> route_task
-> prepare_execution
-> execute_enrichment OR map(execute_enrichment_chunk)
-> validate_results
-> write_output
-> build_report
```

Graph nodes use `app.services.mcp_gateway`, which loads FastMCP tools through
LangChain MCP adapters. Direct `app.tools.local_*` calls are not used from graph
nodes; they are implementation details behind MCP servers and local fallbacks.
In Docker, `MCP_STRICT_TOOLS=true` verifies that the graph uses MCP tools end to
end.

## Routing

- `TABLE_CALC`: deterministic calculations without web.
- `WEB_ENRICH`: external fact lookup.
- `HYBRID`: source lookup plus local calculation.
- `CLARIFICATION_REQUIRED`: unsupported ambiguity.
- `UNSUPPORTED`: safely fail closed.

## Live Demo Paths

- Capitals distance: city coordinates from structured/live sources, then
  haversine distance through the calculation MCP.
- Mountain height: elevation from Wikidata in live mode, with Wikipedia,
  Serper, LLM extraction, and offline seeds as fallbacks.
- Row operations: detect `A`, `B`, `Operation`, and `Value`; resolve unique
  operation labels once; calculate every row deterministically.
- Unknown operation labels such as `suma` use a live OpenRouter classification
  fallback when local matching cannot resolve the label.

The README screenshots are captured with `OFFLINE_DEMO_SEED_FIRST=false`, so
the mountain evidence shown in the UI is `WIKIDATA`, not offline seed data.

## Clarification Loop

- Unknown operation labels are resolved with local matching first, then a batched
  OpenRouter classification fallback.
- If an operation remains ambiguous, the run moves to `awaiting_clarification`
  instead of completing with silent gaps.
- User replies such as `suma = +` are appended to the task and reused as
  explicit operation hints on resume.

## Parallel Enrichment

- After profiling, source-backed large workbooks can switch to `chunk_fanout`
  mode. The graph sends each row chunk to `execute_enrichment_chunk` and merges
  `chunk_updates` with a reducer.
- Source-backed enrichment first deduplicates `FactRequest` objects by structured
  JSON key inside each chunk.
- Unique requests are resolved with `asyncio.gather`.
- A semaphore limits concurrent external calls; configure it with
  `ENRICHMENT_CONCURRENCY`, default `8`.
- LangGraph branch concurrency is controlled separately with
  `GRAPH_FANOUT_CONCURRENCY`, default `4`.
- Chunking is controlled by `GRAPH_FANOUT_THRESHOLD` and `GRAPH_CHUNK_SIZE`,
  both defaulting to `1000`.
- Row order is preserved when `CellUpdate` objects are written back to Excel.

## Health Semantics

`/health` performs a cached live OpenRouter probe. It reports `model_status:
live` only when the completion endpoint responds successfully. It also reports
`data_mode`:

- `live_sources_first` when `OFFLINE_DEMO_SEED_FIRST=false`
- `offline_demo_seed_first` when deterministic offline demo mode is enabled
