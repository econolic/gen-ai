import json
import time
from typing import Any

import httpx
from fastapi import APIRouter

from app.api.error_responses import ERROR_RESPONSES
from app.config import Settings, get_settings
from app.services.mcp_gateway import check_mcp_health

router = APIRouter(tags=["health"], responses=ERROR_RESPONSES)

_OPENROUTER_STATUS_CACHE: dict[str, Any] = {
    "model": None,
    "checked_at": 0.0,
    "payload": None,
}
_OPENROUTER_STATUS_TTL_SECONDS = 60.0


def _openrouter_status(settings: Settings) -> dict[str, Any]:
    if not settings.openrouter_api_key:
        return {
            "model_configured": False,
            "model_status": "not_configured",
            "model_live": False,
            "model_error": None,
            "checked_at": None,
        }

    now = time.time()
    cached = _OPENROUTER_STATUS_CACHE.get("payload")
    if (
        cached
        and _OPENROUTER_STATUS_CACHE.get("model") == settings.openrouter_model
        and now - float(_OPENROUTER_STATUS_CACHE.get("checked_at", 0.0)) < _OPENROUTER_STATUS_TTL_SECONDS
    ):
        return cached

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": json.dumps({"healthcheck": True})},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 32,
    }

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=8.0,
        )
        if response.status_code == 200:
            payload = {
                "model_configured": True,
                "model_status": "live",
                "model_live": True,
                "model_error": None,
                "checked_at": round(now),
            }
        else:
            payload = {
                "model_configured": True,
                "model_status": "error",
                "model_live": False,
                "model_error": f"openrouter_http_{response.status_code}",
                "checked_at": round(now),
            }
    except httpx.HTTPError as exc:
        payload = {
            "model_configured": True,
            "model_status": "error",
            "model_live": False,
            "model_error": exc.__class__.__name__,
            "checked_at": round(now),
        }

    _OPENROUTER_STATUS_CACHE.update(
        {
            "model": settings.openrouter_model,
            "checked_at": now,
            "payload": payload,
        }
    )
    return payload


@router.get("/health")
def health() -> dict[str, Any]:
    """Return readiness and non-secret runtime model metadata for UI smoke checks."""

    settings = get_settings()
    model_status = _openrouter_status(settings)
    return {
        "status": "ok" if model_status["model_live"] or not settings.openrouter_api_key else "degraded",
        "provider": "OpenRouter",
        "model": settings.openrouter_model,
        "data_mode": "offline_demo_seed_first" if settings.offline_demo_seed_first else "live_sources_first",
        **model_status,
    }


@router.get("/health/mcp")
async def mcp_health() -> dict:
    """Return MCP server/tool readiness without exposing secrets."""

    return await check_mcp_health()
