from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import get_settings
from app.schemas.dsl import DSLPlan
from app.schemas.evidence import FactRequest, FactResult
from app.schemas.run import CellUpdate
from app.schemas.workbook import WorkbookProfile
from app.tools.local_calc import execute_formula_dsl as local_execute_formula_dsl
from app.tools.local_calc import haversine_km
from app.tools.local_excel import preview_rows as local_preview_rows
from app.tools.local_excel import profile_workbook as local_profile_workbook
from app.tools.local_excel import read_rows as local_read_rows
from app.tools.local_excel import write_enriched_workbook as local_write_enriched_workbook
from app.tools.local_search import search_numeric_fact as local_search_numeric_fact
from app.tools.local_source import lookup_fact as local_lookup_fact


SERVER_TOOL_NAMES = {
    "excel": {
        "profile_workbook": "profile_workbook_tool",
        "read_rows": "read_rows_tool",
        "preview_rows": "preview_rows_tool",
        "write_enriched_workbook": "write_enriched_workbook_tool",
    },
    "calc": {
        "haversine_distance_km": "haversine_distance_km",
        "execute_formula_dsl": "execute_formula_dsl_tool",
    },
    "source": {
        "lookup_fact": "lookup_fact_tool",
    },
    "search": {
        "search_numeric_fact": "search_numeric_fact_tool",
    },
}

_tools_cache: dict[str, dict[str, BaseTool]] = {}
_tools_lock = asyncio.Lock()
logger = logging.getLogger(__name__)


def _mcp_connections() -> dict[str, dict[str, str]]:
    settings = get_settings()
    urls = {
        "excel": settings.mcp_excel_url,
        "calc": settings.mcp_calc_url,
        "source": settings.mcp_source_url,
        "search": settings.mcp_search_url,
    }
    return {
        name: {"transport": "streamable_http", "url": url}
        for name, url in urls.items()
        if url
    }


def _strict_tools() -> bool:
    return get_settings().mcp_strict_tools


async def _get_server_tools(server_name: str) -> dict[str, BaseTool]:
    if server_name in _tools_cache:
        return _tools_cache[server_name]

    async with _tools_lock:
        if server_name in _tools_cache:
            return _tools_cache[server_name]
        connections = _mcp_connections()
        if server_name not in connections:
            raise RuntimeError(f"MCP server is not configured: {server_name}")
        client = MultiServerMCPClient({server_name: connections[server_name]})
        tools = await client.get_tools(server_name=server_name)
        _tools_cache[server_name] = {tool.name: tool for tool in tools}
        return _tools_cache[server_name]


async def _call_tool(server_name: str, tool_name: str, payload: dict[str, Any]) -> Any:
    started_at = time.perf_counter()
    tools = await _get_server_tools(server_name)
    if tool_name not in tools:
        raise RuntimeError(f"MCP tool not found: {server_name}.{tool_name}")
    settings = get_settings()
    attempts = settings.tool_retry_count + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            result = _normalize_tool_result(
                await asyncio.wait_for(
                    tools[tool_name].ainvoke(payload),
                    timeout=settings.tool_timeout_seconds,
                )
            )
            logger.info(
                "mcp_tool_call",
                extra={
                    "tool_name": f"{server_name}.{tool_name}",
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "status": "ok",
                    "attempt": attempt + 1,
                },
            )
            return result
        except Exception as exc:
            last_error = exc
            logger.warning(
                "mcp_tool_call_retry",
                extra={
                    "tool_name": f"{server_name}.{tool_name}",
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "status": "retrying" if attempt + 1 < attempts else "failed",
                    "attempt": attempt + 1,
                },
            )
    try:
        raise last_error or RuntimeError("MCP tool call failed")
    except Exception:
        logger.exception(
            "mcp_tool_call",
            extra={
                "tool_name": f"{server_name}.{tool_name}",
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "status": "failed",
            },
        )
        raise


async def check_mcp_health() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for server_name, expected_tools in SERVER_TOOL_NAMES.items():
        try:
            tools = await _get_server_tools(server_name)
            missing = sorted(set(expected_tools.values()) - set(tools))
            checks[server_name] = {
                "status": "ok" if not missing else "missing_tools",
                "configured": server_name in _mcp_connections(),
                "tools": sorted(tools),
                "missing_tools": missing,
            }
        except Exception as exc:
            checks[server_name] = {
                "status": "error",
                "configured": server_name in _mcp_connections(),
                "tools": [],
                "missing_tools": sorted(expected_tools.values()),
                "error": str(exc),
            }
    return {
        "status": "ok" if all(item["status"] == "ok" for item in checks.values()) else "degraded",
        "strict": _strict_tools(),
        "servers": checks,
    }


def _parse_text_result(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _normalize_tool_result(result: Any) -> Any:
    if isinstance(result, list) and all(isinstance(item, dict) and "type" in item for item in result):
        if len(result) == 1 and result[0].get("type") == "text":
            return _parse_text_result(str(result[0].get("text", "")))
        normalized = []
        for item in result:
            if item.get("type") == "text":
                normalized.append(_parse_text_result(str(item.get("text", ""))))
            else:
                normalized.append(item)
        return normalized
    if isinstance(result, dict) and result.get("type") == "text":
        return _parse_text_result(str(result.get("text", "")))
    return result


def _normalize_rows_result(result: Any) -> list[dict]:
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return result
    raise TypeError(f"Expected row list from Excel MCP, got {type(result).__name__}")


async def profile_workbook(file_path: str) -> WorkbookProfile:
    """Profile a workbook through the Excel MCP server."""
    try:
        result = await _call_tool(
            "excel",
            SERVER_TOOL_NAMES["excel"]["profile_workbook"],
            {"file_path": file_path},
        )
        return WorkbookProfile.model_validate(result)
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local Excel profile; MCP_STRICT_TOOLS=false")
        return local_profile_workbook(file_path)


async def read_rows(file_path: str, sheet_name: str | None = None) -> list[dict]:
    """Read workbook rows through the Excel MCP server."""
    try:
        result = await _call_tool(
            "excel",
            SERVER_TOOL_NAMES["excel"]["read_rows"],
            {"file_path": file_path, "sheet_name": sheet_name},
        )
        return _normalize_rows_result(result)
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local Excel read; MCP_STRICT_TOOLS=false")
        return local_read_rows(file_path, sheet_name)


async def preview_rows(file_path: str, limit: int = 20, sheet_name: str | None = None) -> list[dict]:
    """Read workbook preview rows through the Excel MCP server."""
    try:
        result = await _call_tool(
            "excel",
            SERVER_TOOL_NAMES["excel"]["preview_rows"],
            {"file_path": file_path, "limit": limit, "sheet_name": sheet_name},
        )
        return _normalize_rows_result(result)
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local Excel preview; MCP_STRICT_TOOLS=false")
        return local_preview_rows(file_path, limit, sheet_name)


async def write_enriched_workbook(
    input_path: str,
    output_path: str,
    updates: list[CellUpdate],
    sheet_name: str | None = None,
) -> str:
    """Write workbook updates through the Excel MCP server."""
    try:
        return await _call_tool(
            "excel",
            SERVER_TOOL_NAMES["excel"]["write_enriched_workbook"],
            {
                "input_path": input_path,
                "output_path": output_path,
                "updates": [update.model_dump() for update in updates],
                "sheet_name": sheet_name,
            },
        )
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local Excel write; MCP_STRICT_TOOLS=false")
        return local_write_enriched_workbook(input_path, output_path, updates, sheet_name)


async def lookup_fact(request: FactRequest) -> FactResult:
    """Resolve a fact through the Source MCP server."""
    try:
        result = await _call_tool(
            "source",
            SERVER_TOOL_NAMES["source"]["lookup_fact"],
            {"request": request.model_dump()},
        )
        return FactResult.model_validate(result)
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local source lookup; MCP_STRICT_TOOLS=false")
        return await local_lookup_fact(request)


async def search_numeric_fact(request: FactRequest) -> FactResult:
    """Resolve a numeric fact through the Search MCP server."""
    try:
        result = await _call_tool(
            "search",
            SERVER_TOOL_NAMES["search"]["search_numeric_fact"],
            {"request": request.model_dump()},
        )
        return FactResult.model_validate(result)
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local search; MCP_STRICT_TOOLS=false")
        return await local_search_numeric_fact(request)


async def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance through the Calc MCP server."""
    try:
        result = await _call_tool(
            "calc",
            SERVER_TOOL_NAMES["calc"]["haversine_distance_km"],
            {"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2},
        )
        return float(result)
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local haversine calc; MCP_STRICT_TOOLS=false")
        return haversine_km(lat1, lon1, lat2, lon2)


async def execute_formula_dsl(rows: list[dict[str, Any]], dsl: DSLPlan) -> list[Any]:
    """Execute formula DSL through the Calc MCP server."""
    try:
        return await _call_tool(
            "calc",
            SERVER_TOOL_NAMES["calc"]["execute_formula_dsl"],
            {"rows": rows, "dsl": dsl.model_dump()},
        )
    except Exception:
        if _strict_tools():
            raise
        logger.warning("Falling back to local formula DSL execution; MCP_STRICT_TOOLS=false")
        return local_execute_formula_dsl(rows, dsl)
