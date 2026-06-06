# 04 Runbook

## Live Docker Demo

```bash
cd excel-agent-platform
cp .env.example .env
OFFLINE_DEMO_SEED_FIRST=false docker compose up --build -d
make docker-health
```

Fill `.env` with OpenRouter and Serper keys before live runs. Do not commit
`.env`.

Open the app:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Optional concurrency tuning:

```bash
ENRICHMENT_CONCURRENCY=8
GRAPH_FANOUT_THRESHOLD=1000
GRAPH_CHUNK_SIZE=1000
GRAPH_FANOUT_CONCURRENCY=4
MCP_STRICT_TOOLS=true
```

`ENRICHMENT_CONCURRENCY` controls source/search calls inside each chunk.
`GRAPH_FANOUT_THRESHOLD` decides when source-backed workbooks switch to
LangGraph fan-out, `GRAPH_CHUNK_SIZE` controls row chunk size, and
`GRAPH_FANOUT_CONCURRENCY` limits concurrent chunk branches.
`MCP_STRICT_TOOLS=true` disables direct local fallbacks and is useful for
Docker smoke tests that must prove MCP tool routing.

## Offline Development Mode

Use this only when external providers are unavailable:

```bash
OFFLINE_DEMO_SEED_FIRST=true docker compose up --build -d
```

In this mode, known capitals and mountains can be resolved from deterministic
demo seeds before live sources.

## Tests

```bash
make eval
```

## Screenshots

```bash
npm install --prefix /tmp/eap-playwright playwright@1.49.1
PLAYWRIGHT_BROWSERS_PATH=/tmp/ms-playwright /tmp/eap-playwright/node_modules/.bin/playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/tmp/ms-playwright make screenshots
```

The screenshots are written to `data/reports/screenshots/` and are referenced by
the README.

## Cleanup

```bash
python3 backend/clean_artifacts.py
```

Cleanup removes runtime uploads, outputs, reports, cache, database files, and
`__pycache__` directories. It preserves README PNG screenshots under
`data/reports/screenshots/`.

## Direct Processing

```python
from app.process import process_excel

result = process_excel("../capitals.xlsx", "find the straight-line distance between the capitals in kilometers for the column distance")
print(result.output_path)
print(result.report_path)
```

## Live Smoke Examples

- OpenRouter status: `make docker-health` should report `model_status: live`.
- Wikidata source: upload `tests/fixtures/mountains_final_project.xlsx`; evidence
  should show `WIKIDATA`.
- LLM resolver: an operation label such as `suma` should resolve to addition when
  local matching cannot classify it.
