from __future__ import annotations

import re
import json
from typing import Any

import httpx

from app.config import get_settings
from app.schemas.evidence import Evidence, FactRequest, FactResult


async def serper_search(query: str, num: int = 5, timeout: float = 10.0) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.serper_api_key:
        return []
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.serper_api_key},
            json={"q": query, "num": num},
        )
        response.raise_for_status()
        data = response.json()
    return data.get("organic", [])


async def search_numeric_fact(request: FactRequest) -> FactResult:
    unit = request.unit or ""
    query = f"{request.entity} {request.attribute} {unit}".strip()
    value_type = request.context.get("value_type") or "number"
    try:
        results = await serper_search(query)
    except Exception as exc:
        return FactResult(request=request, confidence=0.0, error=f"Serper failed: {exc}")

    for item in results:
        snippet = f"{item.get('title', '')} {item.get('snippet', '')}"
        value, extracted_unit = _extract_typed_value(snippet, value_type, request.attribute, unit)
        if value is not None:
            return FactResult(
                request=request,
                value=value,
                unit=extracted_unit or unit or None,
                confidence=0.55,
                evidence=[
                    Evidence(
                        kind="serper",
                        title=item.get("title", query),
                        url=item.get("link"),
                        snippet=item.get("snippet"),
                        confidence=0.55,
                        metadata={"value_type": value_type, "attribute": request.attribute},
                    )
                ],
            )

    # Fallback to LLM search extraction
    snippets = [f"{item.get('title', '')} {item.get('snippet', '')}" for item in results]
    llm_result = await _llm_extract_fact(snippets, request, value_type)
    if llm_result:
        return llm_result

    return FactResult(request=request, confidence=0.0, error=f"No numeric search fact found: {query}")


def _extract_typed_value(
    snippet: str,
    value_type: str,
    attribute: str,
    requested_unit: str,
) -> tuple[Any, str | None]:
    if value_type == "date":
        match = re.search(
            r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b",
            snippet,
        )
        return (match.group(1), None) if match else (None, None)

    if value_type == "string" or attribute == "ceo":
        if attribute == "ceo":
            match = re.search(
                r"(?:CEO|Chief Executive Officer|Chief Executive)\s+(?:is|:)?\s*"
                r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,2})"
                r"(?=\s+(?:according|as|,|\.|$)|$)",
                snippet,
            )
            if match:
                return match.group(1).strip(), None
        return snippet.strip()[:240] if snippet.strip() else None, None

    if requested_unit:
        u_lower = requested_unit.lower()
        if u_lower in {"m", "meter", "meters", "metres", "metre"}:
            unit_pattern = r"(?:meters|metres|m)"
        elif u_lower in {"km", "kilometer", "kilometers", "kilometres", "kilometre"}:
            unit_pattern = r"(?:km|kilometers|kilometres)"
        else:
            unit_pattern = re.escape(requested_unit)
    else:
        unit_pattern = r"(?:m|meters|metres|people|km|%|percent|usd|\$)?"

    match = re.search(
        rf"(-?\d[\d,]*(?:\.\d+)?)\s*({unit_pattern})",
        snippet,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None

    raw_value = match.group(1).replace(",", "")
    value = float(raw_value)
    if value.is_integer():
        value = int(value)
    extracted_unit = (match.group(2) or requested_unit or "").strip() or None
    if extracted_unit == "%":
        extracted_unit = "percent"
    return value, extracted_unit


def _extract_coordinates_from_snippet(snippet: str) -> dict[str, float] | None:
    lat_lon_match = re.search(
        r"(?:lat(?:itude)?|coords|coordinates)\s*[:=]?\s*(-?\d+\.\d+).*?(?:lon(?:gitude)?)\s*[:=]?\s*(-?\d+\.\d+)",
        snippet,
        re.IGNORECASE
    )
    if lat_lon_match:
        try:
            return {"lat": float(lat_lon_match.group(1)), "lon": float(lat_lon_match.group(2))}
        except ValueError:
            pass

    deg_match = re.search(
        r"(-?\d+(?:\.\d+)?)\s*°?\s*([NSns])\s*,?\s*(-?\d+(?:\.\d+)?)\s*°?\s*([EWew])",
        snippet
    )
    if deg_match:
        try:
            lat = float(deg_match.group(1))
            if deg_match.group(2).upper() == "S":
                lat = -lat
            lon = float(deg_match.group(3))
            if deg_match.group(4).upper() == "W":
                lon = -lon
            return {"lat": lat, "lon": lon}
        except ValueError:
            pass

    simple_match = re.search(
        r"\b(-?\d{1,2}\.\d{4,8})\b\s*,\s*\b(-?\d{1,3}\.\d{4,8})\b",
        snippet
    )
    if simple_match:
        try:
            lat = float(simple_match.group(1))
            lon = float(simple_match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return {"lat": lat, "lon": lon}
        except ValueError:
            pass

    return None


async def search_coordinates_fact(request: FactRequest) -> FactResult:
    query = f"{request.entity} coordinates latitude longitude".strip()
    try:
        results = await serper_search(query)
    except Exception as exc:
        return FactResult(request=request, confidence=0.0, error=f"Serper coordinates search failed: {exc}")

    for item in results:
        snippet = f"{item.get('title', '')} {item.get('snippet', '')}"
        coords = _extract_coordinates_from_snippet(snippet)
        if coords:
            return FactResult(
                request=request,
                value=coords,
                unit="degrees",
                confidence=0.6,
                evidence=[
                    Evidence(
                        kind="serper",
                        title=item.get("title", query),
                        url=item.get("link"),
                        snippet=item.get("snippet"),
                        confidence=0.6,
                        metadata={"value_type": "coordinates", "attribute": "coordinates"},
                    )
                ],
            )

    # Fallback to LLM search extraction
    snippets = [f"{item.get('title', '')} {item.get('snippet', '')}" for item in results]
    llm_result = await _llm_extract_fact(snippets, request, "coordinates")
    if llm_result:
        return llm_result

    return FactResult(request=request, confidence=0.0, error=f"No coordinates found in search for: {request.entity}")


async def _llm_extract_fact(snippets: list[str], request: FactRequest, value_type: str) -> FactResult | None:
    settings = get_settings()
    if not settings.openrouter_api_key or not snippets:
        return None

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    prompt = {
        "task": (
            f"Extract the fact value for entity '{request.entity}' and attribute '{request.attribute}' "
            f"from the provided search snippets. The expected value type is '{value_type}' "
            f"(either a number, string, date, or coordinates)."
        ),
        "snippets": snippets[:5],
        "output_schema": {
            "value": "the extracted value (number, string, or coordinates dict {'lat': float, 'lon': float})",
            "confidence": "number from 0 to 1",
            "reason": "explanation of extraction source",
        }
    }

    body = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. Do not explain outside JSON.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 800,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        payload = json.loads(content)
        val = payload.get("value")
        conf = float(payload.get("confidence", 0.5))
        reason = str(payload.get("reason", ""))

        if val is None:
            return None

        if value_type == "number":
            try:
                val = float(str(val).replace(",", "").strip())
                if val.is_integer():
                    val = int(val)
            except ValueError:
                return None
        elif value_type == "coordinates":
            if not isinstance(val, dict) or "lat" not in val or "lon" not in val:
                return None
            try:
                val = {"lat": float(val["lat"]), "lon": float(val["lon"])}
            except ValueError:
                return None

        return FactResult(
            request=request,
            value=val,
            unit=request.unit,
            confidence=conf,
            evidence=[
                Evidence(
                    kind="serper",
                    title=f"LLM extraction for {request.entity}",
                    confidence=conf,
                    snippet=reason,
                )
            ]
        )
    except Exception:
        return None
