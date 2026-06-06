from __future__ import annotations

import ast
from dataclasses import dataclass, field

from app.schemas.dsl import DSLPlan
from app.schemas.task_plan import RouteDecision, TaskPlan
from app.schemas.workbook import WorkbookProfile
from app.tools.local_calc import _SafeExpressionValidator


SUPPORTED_OPERATIONS = {"formula", "group_share", "lookup", "distance"}
FORMULA_FUNCTIONS = {*_SafeExpressionValidator.allowed_functions, "apply_operation"}


@dataclass
class PlanValidationResult:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _column_names(profile: WorkbookProfile) -> set[str]:
    return {column.name for column in profile.first_sheet.columns}


def _expression_column_refs(expression: str | None) -> set[str]:
    if not expression:
        return set()
    tree = ast.parse(expression, mode="eval")
    refs: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "col":
                if node.args and isinstance(node.args[0], ast.Constant):
                    refs.add(str(node.args[0].value))
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if node.id not in FORMULA_FUNCTIONS:
                refs.add(node.id)

    Visitor().visit(tree)
    return refs


def _validate_operation(operation: DSLPlan, columns: set[str]) -> PlanValidationResult:
    result = PlanValidationResult(ok=True)
    if operation.type not in SUPPORTED_OPERATIONS:
        result.errors.append(f"Unsupported operation: {operation.type}")

    source_columns = set(operation.source_columns or [])
    entity_columns = set(operation.entity_columns or [])
    referenced_columns = source_columns | entity_columns

    if operation.type == "formula":
        try:
            if operation.expression == "apply_operation(A, B, Operation)":
                referenced_columns |= set(operation.source_columns)
            else:
                referenced_columns |= _expression_column_refs(operation.expression)
        except SyntaxError as exc:
            result.errors.append(f"Invalid formula expression syntax: {exc.msg}")
        if not operation.expression:
            result.errors.append("Formula operation requires expression")

    if operation.type == "lookup" and not (operation.entity_columns or operation.source_columns):
        result.errors.append("Lookup operation requires entity_columns or source_columns")

    if operation.type == "distance" and len(operation.source_columns) < 4:
        result.errors.append("Distance operation requires city/country columns for both endpoints")

    missing = sorted(column for column in referenced_columns if column not in columns)
    if missing:
        result.errors.append(f"Missing source columns: {', '.join(missing)}")

    result.ok = not result.errors
    return result


def validate_task_plan(plan: TaskPlan, profile: WorkbookProfile) -> PlanValidationResult:
    columns = _column_names(profile)
    result = PlanValidationResult(ok=True)

    if not plan.target_sheet:
        result.errors.append("Target sheet is missing")
    if not plan.target_column:
        result.errors.append("Target column is missing")

    operations = plan.operations or ([plan.dsl] if plan.dsl else [])
    if plan.operation not in {"clarification", "unsupported"} and not operations:
        result.errors.append("Plan has no executable operations")

    for operation in operations:
        operation_result = _validate_operation(operation, columns)
        result.warnings.extend(operation_result.warnings)
        result.errors.extend(operation_result.errors)

    result.ok = not result.errors
    return result


def plan_with_validation(plan: TaskPlan, profile: WorkbookProfile) -> TaskPlan:
    validation = validate_task_plan(plan, profile)
    warnings = [*plan.warnings, *validation.warnings]
    if validation.ok:
        return plan.model_copy(update={"warnings": warnings})

    return TaskPlan(
        task_description=plan.task_description,
        target_sheet=plan.target_sheet or profile.first_sheet.name,
        target_column=plan.target_column or "enriched_value",
        route=RouteDecision(
            route="CLARIFICATION_REQUIRED",
            reason="Generated plan did not pass validation.",
            confidence=0.2,
        ),
        operation="clarification",
        source_columns=plan.source_columns,
        requires_approval=True,
        clarification_question=(
            "Please clarify the task or source columns. Validation errors: "
            + "; ".join(validation.errors)
        ),
        estimated_external_calls=0,
        confidence=0.2,
        warnings=[*warnings, *validation.errors],
    )
