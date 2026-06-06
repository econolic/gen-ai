from app.schemas.run import CellUpdate
from app.schemas.task_plan import TaskPlan


def validate_updates(plan: TaskPlan, updates: list[CellUpdate]) -> tuple[list[CellUpdate], list[str]]:
    warnings: list[str] = []
    valid_updates: list[CellUpdate] = []

    for update in updates:
        if update.error:
            warnings.append(f"Row {update.row_index + 2}: {update.error}")
            valid_updates.append(update)
            continue

        if plan.unit in {"km", "meters"}:
            if not isinstance(update.value, int | float):
                update.error = "Expected numeric value"
                warnings.append(f"Row {update.row_index + 2}: expected numeric value")
            elif update.value < 0:
                update.error = "Expected non-negative value"
                warnings.append(f"Row {update.row_index + 2}: expected non-negative value")

        if update.confidence < 0.5:
            warnings.append(f"Row {update.row_index + 2}: low confidence {update.confidence:.2f}")

        valid_updates.append(update)

    coverage = sum(1 for update in valid_updates if update.error is None) / max(len(valid_updates), 1)
    if coverage < 0.8:
        warnings.append(f"Coverage below target: {coverage:.0%}")

    return valid_updates, warnings
