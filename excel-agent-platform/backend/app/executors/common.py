"""Shared helpers for DSL executors."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import get_settings
from app.schemas.evidence import CoordinatesValue, FactRequest, FactResult


def request_key(request: FactRequest) -> str:
    return request.model_dump_json()


async def resolve_fact_requests(
    requests: list[FactRequest],
    resolver: Callable[[FactRequest], Awaitable[FactResult]],
) -> dict[str, FactResult]:
    """Resolve unique fact requests concurrently with a configured safety limit."""
    unique_requests: dict[str, FactRequest] = {}
    for request in requests:
        unique_requests.setdefault(request_key(request), request)

    semaphore = asyncio.Semaphore(get_settings().enrichment_concurrency)

    async def resolve_one(key: str, request: FactRequest) -> tuple[str, FactResult]:
        async with semaphore:
            return key, await resolver(request)

    resolved = await asyncio.gather(
        *(resolve_one(key, request) for key, request in unique_requests.items())
    )
    return dict(resolved)


def as_number(value: Any) -> float:
    if value is None or value == "":
        raise ValueError("Missing numeric value")
    return float(value)


def format_number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 6)


def extract_coordinates(value: Any) -> tuple[float, float] | None:
    if isinstance(value, CoordinatesValue):
        return value.lat, value.lon
    if not isinstance(value, dict):
        return None
    lat = value.get("lat")
    lon = value.get("lon")
    if lat is None or lon is None:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
            return lat_f, lon_f
    except (ValueError, TypeError):
        pass
    return None
