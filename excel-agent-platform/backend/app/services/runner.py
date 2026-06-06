from app.process import analyze_excel, process_excel
from app.schemas.task_plan import TaskPlan
from app.services.run_store import run_store


def plan_requires_approval(plan: TaskPlan) -> bool:
    risky_routes = {"WEB_ENRICH", "HYBRID"}
    risky_operations = {"lookup", "distance", "hybrid", "regression"}
    return (
        plan.requires_approval
        or plan.route.route in risky_routes
        or any(operation.type in risky_operations for operation in plan.operations)
    )


def analyze_run(run_id: str, input_path: str, task_description: str) -> bool:
    run_store.update(run_id, state="running", progress=0.05, message="Profiling workbook")
    profile, plan, preview = analyze_excel(input_path, task_description)
    awaiting_approval = plan_requires_approval(plan)
    run_store.set_analysis(
        run_id,
        profile,
        plan,
        preview,
        awaiting_approval=awaiting_approval,
    )
    return awaiting_approval


def execute_run(run_id: str, input_path: str, task_description: str) -> None:
    run_store.update(run_id, state="running", progress=0.35, message="Processing workbook")
    try:
        status = run_store.get(run_id)
        result = process_excel(
            input_path,
            task_description,
            run_id=run_id,
            profile=status.profile if status else None,
            plan=status.plan if status else None,
        )
        run_store.complete_from_report(run_id, result.report_path)
    except Exception as exc:
        run_store.update(
            run_id,
            state="failed",
            progress=1.0,
            message="Run failed",
            errors=[str(exc)],
        )
