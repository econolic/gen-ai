import asyncio

import pytest

from app.config import get_settings
from app.graph.nodes import _request_key, _resolve_fact_requests
from app.schemas.evidence import FactRequest, FactResult


@pytest.mark.asyncio
async def test_fact_requests_are_deduplicated_and_resolved_concurrently(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENRICHMENT_CONCURRENCY", "3")
    get_settings.cache_clear()

    active = 0
    max_active = 0
    calls: list[str] = []

    async def resolver(request: FactRequest) -> FactResult:
        nonlocal active, max_active
        calls.append(_request_key(request))
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return FactResult(request=request, value=request.entity, confidence=1.0)

    requests = [
        FactRequest(entity="A", attribute="height", unit="meters"),
        FactRequest(entity="B", attribute="height", unit="meters"),
        FactRequest(entity="C", attribute="height", unit="meters"),
        FactRequest(entity="D", attribute="height", unit="meters"),
        FactRequest(entity="A", attribute="height", unit="meters"),
    ]

    facts = await _resolve_fact_requests(requests, resolver)

    assert len(facts) == 4
    assert len(calls) == 4
    assert max_active == 3
