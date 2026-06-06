from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.planner import build_task_plan
from app.config import get_settings
from app.agents.validator import validate_updates
from app.executors import EXECUTOR_REGISTRY
from app.executors.common import extract_coordinates, request_key, resolve_fact_requests
from app.graph.state import ExcelAgentState
from app.schemas.run import CellUpdate
from app.services import mcp_gateway


# Re-export for backward compatibility with tests that import from nodes
_extract_coordinates = extract_coordinates
_request_key = request_key
_resolve_fact_requests = resolve_fact_requests

SOURCE_BACKED_OPERATIONS = {"distance", "lookup", "hybrid"}


def profile_workbook_node(state: ExcelAgentState) -> ExcelAgentState:
    if state.get("profile") is not None and state.get("rows") is not None:
        return {}

    async def profile_and_read() -> tuple[Any, list[dict]]:
        profile = await mcp_gateway.profile_workbook(state["input_path"])
        rows = await mcp_gateway.read_rows(state["input_path"], profile.first_sheet.name)
        return profile, rows

    profile, rows = asyncio.run(profile_and_read())
    return {**state, "profile": profile, "rows": rows}


def plan_task_node(state: ExcelAgentState) -> ExcelAgentState:
    if state.get("plan") is not None:
        return {}
    plan = build_task_plan(state["task_description"], state["profile"])
    warnings = [*state.get("warnings", []), *plan.warnings]
    return {**state, "plan": plan, "warnings": warnings}


def _chunk_rows(rows: list[dict], chunk_size: int) -> list[list[dict]]:
    return [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]


def prepare_execution_node(state: ExcelAgentState) -> ExcelAgentState:
    """Choose sequential or LangGraph fan-out execution after profiling and planning."""
    settings = get_settings()
    rows = state.get("rows", [])
    plan = state["plan"]
    should_fanout = (
        len(rows) >= settings.graph_fanout_threshold
        and plan.operation in SOURCE_BACKED_OPERATIONS
        and plan.route.route in {"HYBRID", "WEB_ENRICH"}
    )

    if not should_fanout:
        return {
            **state,
            "execution_mode": "single_node",
            "row_chunks": [],
            "fanout_metadata": {
                "enabled": False,
                "row_count": len(rows),
                "reason": "Below threshold or operation does not benefit from source-backed fan-out.",
            },
        }

    chunks = _chunk_rows(rows, settings.graph_chunk_size)
    warnings = [
        *state.get("warnings", []),
        (
            f"Using LangGraph fan-out: {len(rows)} rows split into {len(chunks)} chunks "
            f"of up to {settings.graph_chunk_size} rows."
        ),
    ]
    return {
        **state,
        "execution_mode": "chunk_fanout",
        "row_chunks": chunks,
        "chunk_count": len(chunks),
        "fanout_metadata": {
            "enabled": True,
            "row_count": len(rows),
            "chunk_count": len(chunks),
            "chunk_size": settings.graph_chunk_size,
            "fanout_concurrency": settings.graph_fanout_concurrency,
        },
        "warnings": warnings,
        "chunk_updates": [],
        "processed_chunks": [],
    }


async def _execute_enrichment_async(state: ExcelAgentState) -> list[CellUpdate]:
    plan = state["plan"]
    if plan.route.route == "UNSUPPORTED":
        return [
            CellUpdate(
                row_index=int(row["_row_index"]),
                target_column=plan.target_column,
                error=plan.route.reason,
            )
            for row in state["rows"]
        ]

    if plan.route.route == "CLARIFICATION_REQUIRED":
        return [
            CellUpdate(
                row_index=int(row["_row_index"]),
                target_column=plan.target_column,
                error=plan.clarification_question or plan.route.reason,
            )
            for row in state["rows"]
        ]

    operations = plan.operations or ([plan.dsl] if plan.dsl else [])
    if not operations:
        return [
            CellUpdate(
                row_index=int(row["_row_index"]),
                target_column=plan.target_column,
                error="No executable DSL operation was generated.",
            )
            for row in state["rows"]
        ]

    updates: list[CellUpdate] = []
    working_rows = [dict(row) for row in state["rows"]]
    for dsl in operations:
        executor = EXECUTOR_REGISTRY.get(dsl.type)
        if executor is None:
            updates.extend(
                CellUpdate(
                    row_index=int(row["_row_index"]),
                    target_column=dsl.target_column,
                    error=f"DSL operation is not implemented: {dsl.type}",
                )
                for row in state["rows"]
            )
            continue
        operation_updates = await executor({**state, "rows": working_rows}, dsl)
        updates.extend(operation_updates)
        for update in operation_updates:
            if update.error is None:
                for row in working_rows:
                    if int(row["_row_index"]) == update.row_index:
                        row[update.target_column] = update.value
                        break
    return updates


def execute_enrichment_node(state: ExcelAgentState) -> ExcelAgentState:
    updates = asyncio.run(_execute_enrichment_async(state))
    return {"updates": updates}


def execute_enrichment_chunk_node(state: ExcelAgentState) -> ExcelAgentState:
    updates = asyncio.run(_execute_enrichment_async(state))
    return {
        "chunk_updates": updates,
        "processed_chunks": [int(state.get("chunk_index", 0))],
    }


async def _execute_chunks_async(state: ExcelAgentState) -> list[CellUpdate]:
    settings = get_settings()
    semaphore = asyncio.Semaphore(settings.graph_fanout_concurrency)

    async def execute_one(index: int, rows: list[dict]) -> list[CellUpdate]:
        async with semaphore:
            chunk_state = {
                **state,
                "rows": rows,
                "chunk_index": index,
                "chunk_count": len(state.get("row_chunks", [])),
            }
            return await _execute_enrichment_async(chunk_state)

    chunk_updates = await asyncio.gather(
        *(execute_one(index, rows) for index, rows in enumerate(state.get("row_chunks", [])))
    )
    return [update for updates in chunk_updates for update in updates]


def execute_enrichment_fanout_fallback_node(state: ExcelAgentState) -> ExcelAgentState:
    updates = asyncio.run(_execute_chunks_async(state))
    return {
        "updates": updates,
        "processed_chunks": list(range(len(state.get("row_chunks", [])))),
    }


def validate_results_node(state: ExcelAgentState) -> ExcelAgentState:
    source_updates = state.get("chunk_updates") or state["updates"]
    ordered_updates = sorted(source_updates, key=lambda update: update.row_index)
    updates, validation_warnings = validate_updates(state["plan"], ordered_updates)
    return {"updates": updates, "warnings": [*state.get("warnings", []), *validation_warnings]}


def write_output_node(state: ExcelAgentState) -> ExcelAgentState:
    async def write_and_preview() -> tuple[str, list[dict]]:
        output_path = await mcp_gateway.write_enriched_workbook(
            state["input_path"],
            state["output_path"],
            state["updates"],
            state["plan"].target_sheet,
        )
        preview = await mcp_gateway.preview_rows(
            output_path,
            limit=20,
            sheet_name=state["plan"].target_sheet,
        )
        return output_path, preview

    output_path, preview = asyncio.run(write_and_preview())
    return {"output_path": output_path, "preview": preview}


def _build_performance_report(state: ExcelAgentState) -> dict[str, Any]:
    settings = get_settings()
    updates = state.get("updates", [])
    rows = state.get("rows", [])
    row_count = len(rows)
    evidence_items = [
        evidence
        for update in updates
        for evidence in update.evidence
        if evidence.get("kind") != "calculation"
    ]
    unique_evidence_keys = {
        (
            evidence.get("kind"),
            evidence.get("title"),
            evidence.get("url"),
            json.dumps(evidence.get("metadata", {}), sort_keys=True, default=str),
        )
        for evidence in evidence_items
    }
    source_counts = {
        source: sum(1 for evidence in unique_evidence_keys if evidence[0] == source)
        for source in ["offline_demo_seed", "seed_fact", "wikidata", "wikipedia", "serper"]
    }
    external_calls = len(unique_evidence_keys)
    fact_uses = len(evidence_items)
    cache_hits = max(0, fact_uses - external_calls)
    total_latency_ms = round((time.perf_counter() - state.get("started_at_perf", time.perf_counter())) * 1000, 2)

    return {
        "row_count": row_count,
        "update_count": len(updates),
        "failed_updates": sum(1 for update in updates if update.error),
        "unique_fact_requests": external_calls,
        "external_calls": external_calls,
        "cache_hits": cache_hits,
        "cache_hit_rate": round(cache_hits / fact_uses, 4) if fact_uses else 0.0,
        "avg_latency_ms_per_row": round(total_latency_ms / row_count, 2) if row_count else 0.0,
        "total_latency_ms": total_latency_ms,
        "max_concurrency": settings.enrichment_concurrency,
        "fanout_enabled": bool(state.get("fanout_metadata", {}).get("enabled")),
        "llm_calls": 0,
        "serper_calls": source_counts["serper"],
        "wikidata_calls": source_counts["wikidata"],
        "wikipedia_calls": source_counts["wikipedia"],
        "seed_calls": source_counts["offline_demo_seed"] + source_counts["seed_fact"],
    }


def build_report_node(state: ExcelAgentState) -> ExcelAgentState:
    report_path = Path(state["report_path"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "run_id": state["run_id"],
        "created_at": datetime.now(UTC).isoformat(),
        "task_description": state["task_description"],
        "input_path": state["input_path"],
        "output_path": state["output_path"],
        "plan": state["plan"].model_dump(),
        "profile": state["profile"].model_dump(),
        "updates": [update.model_dump() for update in state["updates"]],
        "preview": state.get("preview", []),
        "fanout": state.get("fanout_metadata", {"enabled": False}),
        "performance": _build_performance_report(state),
        "processed_chunks": state.get("processed_chunks", []),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report_path": str(report_path)}
