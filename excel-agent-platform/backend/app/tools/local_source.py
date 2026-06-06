from __future__ import annotations

import re
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.schemas.evidence import Evidence, FactRequest, FactResult
from app.config import get_settings
from app.services.chroma_memory import remember_fact_result
from app.services.sqlite_store import sqlite_store
from app.tools.local_search import search_coordinates_fact, search_numeric_fact

logger = logging.getLogger(__name__)

_SEEDS_DIR = Path(__file__).resolve().parents[2] / "data" / "seeds"


def _load_seed_coordinates() -> dict[str, tuple[float, float]]:
    path = _SEEDS_DIR / "capitals.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: (coords[0], coords[1]) for key, coords in data.items()}


def _load_seed_heights() -> dict[str, int]:
    path = _SEEDS_DIR / "mountains.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


CAPITAL_COORDINATES: dict[str, tuple[float, float]] = _load_seed_coordinates()
MOUNTAIN_HEIGHTS_M: dict[str, int] = _load_seed_heights()


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _context_country(request: FactRequest) -> str:
    return _normalize(
        request.context.get("country")
        or request.context.get("Country")
        or request.context.get("Country_From")
        or request.context.get("Country_To")
        or ""
    )


def _seed_coordinate(request: FactRequest) -> FactResult | None:
    country = _context_country(request)
    key = f"{_normalize(request.entity)}|{country}"
    coords = CAPITAL_COORDINATES.get(key)
    if coords is None:
        coords = CAPITAL_COORDINATES.get(_normalize(request.entity))
    if coords is None:
        return None
    return FactResult(
        request=request,
        value={"lat": coords[0], "lon": coords[1]},
        unit="degrees",
        confidence=0.98,
        evidence=[
            Evidence(
                kind="offline_demo_seed",
                title=f"Seed coordinates for {request.entity}",
                confidence=0.98,
                metadata={"country": country},
            )
        ],
    )


def _seed_height(request: FactRequest) -> FactResult | None:
    country = _context_country(request)
    key = f"{_normalize(request.entity)}|{country}"
    height = MOUNTAIN_HEIGHTS_M.get(key)
    if height is None:
        height = MOUNTAIN_HEIGHTS_M.get(_normalize(request.entity))
    if height is None:
        return None
    return FactResult(
        request=request,
        value=height,
        unit="meters",
        confidence=0.98,
        evidence=[
            Evidence(
                kind="offline_demo_seed",
                title=f"Seed elevation for {request.entity}",
                confidence=0.98,
                metadata={"country": country},
            )
        ],
    )


def _seed_fact(request: FactRequest) -> FactResult | None:
    if request.attribute == "coordinates":
        return _seed_coordinate(request)
    if request.attribute in {"height", "elevation"}:
        return _seed_height(request)
    return None


async def lookup_wikidata_fact(request: FactRequest, timeout: float = 6.0) -> FactResult | None:
    """Best-effort generic Wikidata lookup with candidate validation."""

    prop_map = {
        "coordinates": "P625",
        "height": "P2044",
        "elevation": "P2044",
        "population": "P1082",
        "ceo": "P169",
    }
    target_prop = prop_map.get(request.attribute)
    if not target_prop:
        return None

    search_url = "https://www.wikidata.org/w/api.php"
    country = _context_country(request)
    cleaned_country = country.replace("/", " ").strip()

    # Try searching with country suffix first, then fallback to just entity
    search_queries = []
    if cleaned_country:
        search_queries.append(f"{request.entity} {cleaned_country}")
    search_queries.append(request.entity)

    headers = {
        "User-Agent": "ExcelAgentPlatform/1.0 (contact@example.com)"
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for query in search_queries:
            params = {
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "search": query,
                "limit": 5,
            }
            try:
                search_response = await client.get(search_url, params=params)
                search_response.raise_for_status()
                search_data = search_response.json()
                results = search_data.get("search", [])
                if not results:
                    continue
            except Exception:
                logger.debug("Wikidata API search request failed for query %s", query, exc_info=True)
                continue

            for item in results:
                entity_id = item["id"]
                try:
                    entity_response = await client.get(
                        f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
                    )
                    entity_response.raise_for_status()
                    entity = entity_response.json()["entities"][entity_id]
                    claims = entity.get("claims", {})
                except Exception:
                    logger.debug("Failed to fetch Wikidata entity data for ID %s", entity_id, exc_info=True)
                    continue

                if target_prop in claims:
                    title = entity.get("labels", {}).get("en", {}).get("value") or request.entity

                    if request.attribute == "coordinates":
                        value = claims["P625"][0]["mainsnak"]["datavalue"]["value"]
                        return FactResult(
                            request=request,
                            value={"lat": value["latitude"], "lon": value["longitude"]},
                            unit="degrees",
                            confidence=0.92,
                            evidence=[
                                Evidence(
                                    kind="wikidata",
                                    title=title,
                                    url=f"https://www.wikidata.org/wiki/{entity_id}",
                                    confidence=0.92,
                                )
                            ],
                        )

                    if request.attribute in {"height", "elevation"}:
                        value = claims["P2044"][0]["mainsnak"]["datavalue"]["value"]
                        amount = float(value["amount"])
                        return FactResult(
                            request=request,
                            value=round(amount),
                            unit="meters",
                            confidence=0.92,
                            evidence=[
                                Evidence(
                                    kind="wikidata",
                                    title=title,
                                    url=f"https://www.wikidata.org/wiki/{entity_id}",
                                    confidence=0.92,
                                )
                            ],
                        )

                    if request.attribute == "population":
                        value = claims["P1082"][0]["mainsnak"]["datavalue"]["value"]
                        amount = float(value["amount"])
                        return FactResult(
                            request=request,
                            value=round(amount),
                            unit=request.unit or "people",
                            confidence=0.88,
                            evidence=[
                                Evidence(
                                    kind="wikidata",
                                    title=title,
                                    url=f"https://www.wikidata.org/wiki/{entity_id}",
                                    confidence=0.88,
                                )
                            ],
                        )

                    if request.attribute == "ceo":
                        value = claims["P169"][0]["mainsnak"]["datavalue"]["value"]
                        ceo_id = value.get("id")
                        ceo_title = ceo_id
                        if ceo_id:
                            try:
                                label_response = await client.get(
                                    f"https://www.wikidata.org/wiki/Special:EntityData/{ceo_id}.json"
                                )
                                label_response.raise_for_status()
                                ceo_entity = label_response.json()["entities"][ceo_id]
                                ceo_title = ceo_entity.get("labels", {}).get("en", {}).get("value", ceo_id)
                            except Exception:
                                logger.debug("Failed to resolve label for Wikidata CEO ID %s", ceo_id, exc_info=True)
                                ceo_title = ceo_id
                        return FactResult(
                            request=request,
                            value=ceo_title,
                            confidence=0.85,
                            evidence=[
                                Evidence(
                                    kind="wikidata",
                                    title=title,
                                    url=f"https://www.wikidata.org/wiki/{entity_id}",
                                    confidence=0.85,
                                    metadata={"property": "P169"},
                                )
                            ],
                        )
    return None


async def lookup_wikipedia_summary(request: FactRequest, timeout: float = 4.0) -> FactResult | None:
    """Best-effort Wikipedia summary fallback for elevation-like facts."""

    title = quote(request.entity.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        if response.status_code >= 400:
            return None
        data = response.json()
    extract = data.get("extract") or ""
    if request.attribute in {"height", "elevation"}:
        match = re.search(r"(\d{4,5})\s*m", extract)
        if match:
            return FactResult(
                request=request,
                value=int(match.group(1)),
                unit="meters",
                confidence=0.65,
                evidence=[
                    Evidence(
                        kind="wikipedia",
                        title=data.get("title", request.entity),
                        url=data.get("content_urls", {}).get("desktop", {}).get("page"),
                        snippet=extract[:400],
                        confidence=0.65,
                    )
                ],
            )
    return None


def _cache_key(request: FactRequest) -> str:
    payload = request.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(request: FactRequest) -> FactResult | None:
    with sqlite_store.connect() as connection:
        row = connection.execute(
            "SELECT payload FROM fact_cache WHERE cache_key = ?",
            (_cache_key(request),),
        ).fetchone()
    if row is None:
        return None
    return FactResult.model_validate_json(row["payload"])


def _cache_put(result: FactResult) -> FactResult:
    if result.error or result.confidence <= 0:
        return result
    with sqlite_store.connect() as connection:
        connection.execute(
            """
            INSERT INTO fact_cache (cache_key, payload, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload = excluded.payload,
                created_at = CURRENT_TIMESTAMP
            """,
            (_cache_key(result.request), result.model_dump_json()),
        )
    remember_fact_result(result)
    return result


async def lookup_fact(request: FactRequest) -> FactResult:
    if get_settings().offline_demo_seed_first:
        seed = _seed_fact(request)
        if seed:
            return _cache_put(seed)

    cached = _cache_get(request)
    if cached:
        return cached

    try:
        wikidata_result = await lookup_wikidata_fact(request)
        if wikidata_result:
            return _cache_put(wikidata_result)
    except Exception:
        logger.debug("Wikidata lookup failed for %s/%s", request.entity, request.attribute, exc_info=True)

    try:
        wikipedia_result = await lookup_wikipedia_summary(request)
        if wikipedia_result:
            return _cache_put(wikipedia_result)
    except Exception:
        logger.debug("Wikipedia summary failed for %s/%s", request.entity, request.attribute, exc_info=True)

    try:
        if request.attribute == "coordinates":
            search_result = await search_coordinates_fact(request)
        else:
            search_result = await search_numeric_fact(request)
        if not search_result.error:
            return _cache_put(search_result)
    except Exception:
        logger.debug("Search fallback failed for %s/%s", request.entity, request.attribute, exc_info=True)

    seed = _seed_fact(request)
    if seed:
        return _cache_put(seed)

    return FactResult(
        request=request,
        confidence=0.0,
        error=f"No fact found for {request.entity} / {request.attribute}",
    )
