from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import asyncio
import time

from app.agents.planner import build_task_plan
from app.config import get_settings
from app.graph.builder import build_excel_agent_graph, run_sequential_graph
from app.graph.state import ExcelAgentState
from app.schemas.run import ProcessResult
from app.schemas.task_plan import TaskPlan
from app.schemas.workbook import WorkbookProfile
from app.services import mcp_gateway


def _default_output_path(input_path: Path, run_id: str) -> Path:
    settings = get_settings()
    return settings.outputs_dir / f"{input_path.stem}_{run_id[:8]}_enriched.xlsx"


def _default_report_path(input_path: Path, run_id: str) -> Path:
    settings = get_settings()
    return settings.reports_dir / f"{input_path.stem}_{run_id[:8]}_report.json"


def process_excel(
    file_path: str,
    task_description: str,
    output_path: str | None = None,
    run_id: str | None = None,
    profile: WorkbookProfile | None = None,
    plan: TaskPlan | None = None,
) -> ProcessResult:
    """Process one Excel workbook and write an enriched output workbook."""

    settings = get_settings()
    settings.ensure_data_dirs()
    input_path = Path(file_path)
    current_run_id = run_id or str(uuid4())
    resolved_output_path = Path(output_path) if output_path else _default_output_path(input_path, current_run_id)
    report_path = _default_report_path(input_path, current_run_id)

    initial_state: ExcelAgentState = {
        "run_id": current_run_id,
        "input_path": str(input_path),
        "output_path": str(resolved_output_path),
        "report_path": str(report_path),
        "task_description": task_description,
        "started_at_perf": time.perf_counter(),
        "warnings": [],
        "errors": [],
    }
    if profile is not None:
        initial_state["profile"] = profile
        initial_state["rows"] = asyncio.run(mcp_gateway.read_rows(str(input_path), profile.first_sheet.name))
    if plan is not None:
        initial_state["plan"] = plan

    graph = build_excel_agent_graph()
    if graph is None:
        final_state = run_sequential_graph(initial_state)
    else:
        final_state = graph.invoke(
            initial_state,
            config={"max_concurrency": settings.graph_fanout_concurrency},
        )

    return ProcessResult(
        run_id=current_run_id,
        output_path=final_state["output_path"],
        report_path=final_state["report_path"],
        plan=final_state["plan"],
        preview=final_state.get("preview", []),
        warnings=final_state.get("warnings", []),
        errors=final_state.get("errors", []),
    )


def analyze_excel(file_path: str, task_description: str) -> tuple[WorkbookProfile, TaskPlan, list[dict]]:
    """Profile a workbook and produce a typed plan without executing enrichment."""

    async def analyze() -> tuple[WorkbookProfile, list[dict]]:
        profile = await mcp_gateway.profile_workbook(file_path)
        rows = await mcp_gateway.preview_rows(file_path, limit=20, sheet_name=profile.first_sheet.name)
        return profile, rows

    profile, preview = asyncio.run(analyze())
    plan = build_task_plan(task_description, profile)
    return profile, plan, preview
