from app.agents.planner import build_task_plan
from app.schemas.workbook import ColumnProfile, SheetProfile, WorkbookProfile


def _profile(columns: list[str], rows: list[dict] | None = None) -> WorkbookProfile:
    return WorkbookProfile(
        file_path="eval.xlsx",
        sheets=[
            SheetProfile(
                name="Sheet1",
                row_count=max(1, len(rows or [])),
                column_count=len(columns),
                columns=[
                    ColumnProfile(name=column, non_null_count=1, null_count=0, dtype="object")
                    for column in columns
                ],
                sample_rows=rows or [{column: "x" for column in columns}],
            )
        ],
    )


def test_planner_routing_accuracy():
    cases = [
        ("A+B", _profile(["A", "B", "Value"]), "TABLE_CALC"),
        ("обчисли частку продажів", _profile(["Product", "Sales", "Share"], [{"Product": "A", "Sales": 1, "Share": None}]), "TABLE_CALC"),
        ("додай висоту гір", _profile(["Mountain", "Country", "height"]), "WEB_ENRICH"),
        ("додай населення міста", _profile(["City", "Country", "population"]), "WEB_ENRICH"),
        ("відшукай населення і розрахуй на душу", _profile(["City", "Country", "Sales", "Population", "Sales_per_capita"]), "HYBRID"),
        ("make it pretty", _profile(["Name", "Value"]), "CLARIFICATION_REQUIRED"),
    ]

    correct = 0
    for task, profile, expected_route in cases:
        plan = build_task_plan(task, profile)
        correct += int(plan.route.route == expected_route)

    assert correct / len(cases) >= 0.9
