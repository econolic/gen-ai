from app.agents.planner import build_task_plan
from app.schemas.workbook import ColumnProfile, SheetProfile, WorkbookProfile


def _profile(columns: list[str]) -> WorkbookProfile:
    return WorkbookProfile(
        file_path="demo.xlsx",
        sheets=[
            SheetProfile(
                name="Sheet1",
                row_count=2,
                column_count=len(columns),
                columns=[
                    ColumnProfile(name=column, non_null_count=2, null_count=0, dtype="object")
                    for column in columns
                ],
                sample_rows=[],
            )
        ],
    )


def test_plans_capital_distance_route():
    profile = _profile(["Capital_From", "Country_From", "Capital_To", "Country_To", "distance"])
    plan = build_task_plan("find the straight-line distance between the capitals in kilometers for the column distance", profile)
    assert plan.operation == "distance"
    assert plan.operations[0].type == "distance"
    assert plan.route.route == "HYBRID"
    assert plan.target_column == "distance"


def test_plans_mountain_height_route():
    profile = _profile(["Mountain", "Country", "height"])
    plan = build_task_plan("add the height of the mountains in meters to the column height", profile)
    assert plan.operation == "lookup"
    assert plan.operations[0].attribute == "height"
    assert plan.route.route == "WEB_ENRICH"
    assert plan.target_column == "height"


def test_plans_row_operation_and_uses_value_as_target():
    profile = _profile(["A", "B", "Operation", "Value"])
    plan = build_task_plan(
        "calculate the values of columns A and B according to the operation from column Operation "
        "and save the result in column Value",
        profile,
    )
    assert plan.operation == "formula"
    assert plan.operations[0].type == "formula"
    assert plan.route.route == "TABLE_CALC"
    assert plan.target_column == "Value"
    assert plan.source_columns == ["A", "B", "Operation"]


def test_plans_population_as_generic_lookup():
    profile = _profile(["City", "Country", "population"])
    plan = build_task_plan("find population for each city in column population", profile)
    assert plan.operation == "lookup"
    assert plan.operations[0].attribute == "population"
    assert plan.operations[0].value_type == "number"


def test_llm_planner_fallback(monkeypatch):
    from app.agents import planner
    from app.schemas.task_plan import RouteDecision, TaskPlan
    from app.schemas.dsl import DSLPlan

    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-key")
    from app.config import get_settings
    get_settings.cache_clear()

    async def mock_llm_build(task, prof):
        return TaskPlan(
            task_description=task,
            target_sheet="Sheet1",
            target_column="custom_column",
            route=RouteDecision(route="TABLE_CALC", reason="LLM chosen"),
            operation="formula",
            dsl=DSLPlan(type="formula", target_column="custom_column", expression="col('A') * 2")
        )

    monkeypatch.setattr(planner, "_llm_build_task_plan", mock_llm_build)

    profile = _profile(["A", "custom_column"])
    plan = build_task_plan("multiply column A by 2", profile)

    assert plan.target_column == "custom_column"
    assert plan.route.route == "TABLE_CALC"
    assert plan.dsl.expression == "col('A') * 2"
