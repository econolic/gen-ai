from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.task_plan import TaskPlan
from app.schemas.workbook import WorkbookProfile

RunState = Literal[
    "queued",
    "running",
    "awaiting_approval",
    "awaiting_clarification",
    "completed",
    "failed",
]


class CellUpdate(BaseModel):
    row_index: int
    target_column: str
    value: int | float | str | dict[str, Any] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    error: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class RunStatus(BaseModel):
    run_id: str
    state: RunState
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = ""
    input_path: str | None = None
    output_path: str | None = None
    report_path: str | None = None
    task_description: str | None = None
    profile: WorkbookProfile | None = None
    plan: TaskPlan | None = None
    preview: list[dict[str, Any]] = Field(default_factory=list)
    updates: list[CellUpdate] = Field(default_factory=list)
    performance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


class ProcessResult(BaseModel):
    run_id: str
    output_path: str
    report_path: str
    plan: TaskPlan
    preview: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RunCreateResponse(BaseModel):
    run_id: str


class ApprovalResponse(BaseModel):
    run_id: str
    status: str


class ClarificationResponse(BaseModel):
    run_id: str
    status: str


class PreviewResponse(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
