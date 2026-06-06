import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.error_responses import ERROR_RESPONSES
from app.services.file_store import save_upload
from app.services.run_store import run_store
from app.services.runner import analyze_run, execute_run
from app.schemas.run import (
    ApprovalResponse,
    ClarificationResponse,
    PreviewResponse,
    RunCreateResponse,
    RunStatus,
)
from app.schemas.task_plan import TaskPlan

router = APIRouter(prefix="/api/runs", tags=["runs"], responses=ERROR_RESPONSES)


@router.post(
    "",
    response_model=RunCreateResponse,
    summary="Create an Excel enrichment run",
    description=(
        "Upload an Excel workbook and a natural-language task. The backend stores the file, "
        "creates a run id, and starts the LangGraph enrichment workflow in the background."
    ),
)
async def create_run(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    task_description: str = Form(...),
) -> dict[str, str]:
    """Create a run, analyze its plan, and auto-run only safe local tasks."""

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xlsm files are supported")

    input_path = await save_upload(file)
    status = run_store.create(str(input_path), task_description)
    try:
        awaiting_approval = await asyncio.to_thread(
            analyze_run,
            status.run_id,
            str(input_path),
            task_description,
        )
    except Exception as exc:
        run_store.update(
            status.run_id,
            state="failed",
            progress=1.0,
            message="Run analysis failed",
            errors=[str(exc)],
        )
        raise HTTPException(status_code=500, detail=f"Run analysis failed: {exc}") from exc
    if not awaiting_approval:
        background_tasks.add_task(execute_run, status.run_id, str(input_path), task_description)
    return {"run_id": status.run_id}


@router.get(
    "/{run_id}",
    response_model=RunStatus,
    summary="Get run status",
    description="Return current state, progress, generated plan, preview rows, warnings, and errors.",
)
def get_run(run_id: str) -> RunStatus:
    """Fetch the current lifecycle status for a run."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@router.get(
    "/{run_id}/plan",
    response_model=TaskPlan,
    summary="Get generated task plan",
    description="Return the typed TaskPlan produced by the planner/router agents.",
)
def get_plan(run_id: str) -> TaskPlan:
    """Fetch the typed plan once the planner has completed."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if status.plan is None:
        raise HTTPException(status_code=409, detail="Plan is not ready yet")
    return status.plan


@router.patch(
    "/{run_id}/plan",
    response_model=TaskPlan,
    summary="Edit generated task plan before approval",
    description="Allow the UI to adjust the target column before a risky plan is approved.",
)
def update_plan(run_id: str, target_column: str = Form(...)) -> TaskPlan:
    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if status.plan is None:
        raise HTTPException(status_code=409, detail="Plan is not ready yet")
    if status.state != "awaiting_approval":
        raise HTTPException(status_code=409, detail="Plan can only be edited before approval")

    operations = [
        operation.model_copy(update={"target_column": target_column})
        for operation in status.plan.operations
    ]
    plan = status.plan.model_copy(
        update={
            "target_column": target_column,
            "source_columns": status.plan.source_columns,
            "dsl": operations[0] if operations else None,
            "operations": operations,
        }
    )
    run_store.update(run_id, plan=plan)
    return plan


@router.post(
    "/{run_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve a generated plan",
    description="Approve a risky generated plan and start execution.",
)
def approve_run(run_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Approve a run plan in workflows that require human confirmation."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if status.plan is None:
        raise HTTPException(status_code=409, detail="Plan is not ready yet")
    if status.state not in {"awaiting_approval", "awaiting_clarification"}:
        raise HTTPException(status_code=409, detail=f"Run is not waiting for approval: {status.state}")
    run_store.update(
        run_id,
        state="running",
        progress=0.3,
        message="Plan approved; execution queued",
        clarification_question=None,
    )
    background_tasks.add_task(execute_run, run_id, status.input_path or "", status.task_description or "")
    return {"run_id": run_id, "status": "approved"}


@router.post(
    "/{run_id}/clarify",
    response_model=ClarificationResponse,
    summary="Resume a run with clarification",
    description=(
        "Append a user's clarification to the original task and resume processing the same "
        "uploaded workbook."
    ),
)
def clarify_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    clarification: str = Form(...),
) -> dict[str, str]:
    """Resume a run after the user explains an ambiguous request or data value."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not status.input_path or not status.task_description:
        raise HTTPException(status_code=409, detail="Run cannot be resumed")
    task_description = f"{status.task_description}\n\nUser clarification: {clarification}"
    run_store.update(
        run_id,
        state="running",
        progress=0.05,
        message="Processing clarification",
        task_description=task_description,
        clarification_question=None,
        profile=None,
        plan=None,
        preview=[],
        warnings=[],
        errors=[],
    )
    background_tasks.add_task(execute_run, run_id, status.input_path, task_description)
    return {"run_id": run_id, "status": "resumed"}


@router.get(
    "/{run_id}/preview",
    response_model=PreviewResponse,
    summary="Preview enriched rows",
    description="Return the first enriched rows for UI inspection before downloading the workbook.",
)
def get_preview(run_id: str) -> dict[str, list[dict]]:
    """Fetch preview rows from the enriched workbook."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"rows": status.preview}


@router.get(
    "/{run_id}/download",
    summary="Download enriched workbook",
    description="Download the generated Excel workbook with enriched target columns.",
)
def download_output(run_id: str) -> FileResponse:
    """Download the enriched `.xlsx` output file for a completed run."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not status.output_path or not Path(status.output_path).exists():
        raise HTTPException(status_code=409, detail="Output is not ready yet")
    return FileResponse(
        status.output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=Path(status.output_path).name,
    )


@router.get(
    "/{run_id}/report",
    summary="Download run report",
    description="Download the JSON evidence report with per-cell confidence, evidence, and warnings.",
)
def download_report(run_id: str) -> FileResponse:
    """Download the JSON report generated for a completed enrichment run."""

    status = run_store.get(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not status.report_path or not Path(status.report_path).exists():
        raise HTTPException(status_code=409, detail="Report is not ready yet")
    return FileResponse(status.report_path, media_type="application/json", filename=Path(status.report_path).name)
