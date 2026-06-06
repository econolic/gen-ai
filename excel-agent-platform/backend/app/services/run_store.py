from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.schemas.run import CellUpdate, RunStatus
from app.schemas.task_plan import TaskPlan
from app.schemas.workbook import WorkbookProfile
from app.services.sqlite_store import sqlite_store


def _build_clarification_question(report: dict) -> str | None:
    plan = TaskPlan.model_validate(report["plan"])
    if plan.route.route == "CLARIFICATION_REQUIRED":
        return plan.clarification_question or plan.route.reason

    operation_errors = [
        item
        for item in report.get("updates", [])
        if str(item.get("error") or "").startswith("Could not understand Operation")
    ]
    if not operation_errors:
        return None

    examples = []
    for item in operation_errors[:5]:
        evidence = item.get("evidence") or []
        metadata = evidence[0].get("metadata", {}) if evidence else {}
        label = metadata.get("operation_label", "")
        examples.append(f"row {int(item['row_index']) + 2}: {label}")
    return (
        "Some values in the Operation column are ambiguous. Please explain how to interpret "
        f"these operations: {', '.join(examples)}."
    )


class SQLiteRunStore:
    def create(self, input_path: str, task_description: str) -> RunStatus:
        run_id = str(uuid4())
        status = RunStatus(
            run_id=run_id,
            state="queued",
            progress=0.0,
            message="Run queued",
            input_path=input_path,
            task_description=task_description,
        )
        self.put(status)
        return status

    def put(self, status: RunStatus) -> RunStatus:
        with sqlite_store.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (run_id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (status.run_id, status.model_dump_json()),
            )
        return status

    def get(self, run_id: str) -> RunStatus | None:
        with sqlite_store.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunStatus.model_validate_json(row["payload"])

    def update(self, run_id: str, **updates) -> RunStatus:
        current = self.get(run_id)
        if current is None:
            raise KeyError(run_id)
        merged = current.model_copy(update=updates)
        return self.put(merged)

    def complete_from_report(self, run_id: str, report_path: str) -> RunStatus:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        clarification_question = _build_clarification_question(report)
        state = "awaiting_clarification" if clarification_question else "completed"
        message = "Clarification required" if clarification_question else "Run completed"
        return self.update(
            run_id,
            state=state,
            progress=1.0,
            message=message,
            output_path=report.get("output_path"),
            report_path=report_path,
            plan=TaskPlan.model_validate(report["plan"]),
            profile=WorkbookProfile.model_validate(report["profile"]),
            preview=report.get("preview", []),
            updates=[CellUpdate.model_validate(item) for item in report.get("updates", [])],
            performance=report.get("performance", {}),
            warnings=report.get("warnings", []),
            errors=report.get("errors", []),
            clarification_question=clarification_question,
        )

    def set_analysis(
        self,
        run_id: str,
        profile: WorkbookProfile,
        plan: TaskPlan,
        preview: list[dict],
        *,
        awaiting_approval: bool,
    ) -> RunStatus:
        return self.update(
            run_id,
            state="awaiting_approval" if awaiting_approval else "running",
            progress=0.25 if awaiting_approval else 0.35,
            message="Awaiting plan approval" if awaiting_approval else "Executing approved plan",
            profile=profile,
            plan=plan,
            preview=preview,
            warnings=plan.warnings,
        )


run_store = SQLiteRunStore()
