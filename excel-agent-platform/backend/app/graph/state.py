import operator
from typing import Annotated, Any, TypedDict

from app.schemas.run import CellUpdate
from app.schemas.task_plan import TaskPlan
from app.schemas.workbook import WorkbookProfile


class ExcelAgentState(TypedDict, total=False):
    run_id: str
    input_path: str
    output_path: str
    report_path: str
    task_description: str
    started_at_perf: float
    profile: WorkbookProfile
    plan: TaskPlan
    rows: list[dict]
    row_chunks: list[list[dict]]
    execution_mode: str
    chunk_index: int
    chunk_count: int
    fanout_metadata: dict[str, Any]
    chunk_updates: Annotated[list[CellUpdate], operator.add]
    updates: list[CellUpdate]
    processed_chunks: Annotated[list[int], operator.add]
    preview: list[dict]
    warnings: list[str]
    errors: list[str]
