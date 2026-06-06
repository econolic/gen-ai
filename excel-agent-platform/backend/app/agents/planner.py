import re
import json
import logging
import httpx
import asyncio

from app.config import get_settings
from app.agents.plan_validator import plan_with_validation, validate_task_plan
from app.agents.router import route_task
from app.schemas.dsl import DSLPlan
from app.schemas.task_plan import RouteDecision, TaskPlan
from app.schemas.workbook import WorkbookProfile


def _column_names(profile: WorkbookProfile) -> list[str]:
    return [column.name for column in profile.first_sheet.columns]


def _extract_target_column(task_description: str, profile: WorkbookProfile, columns: list[str]) -> str | None:
    text = task_description.strip()
    patterns = [
        r"(?:колонки|колонку|колонці|колонцы|column)\s+[`\"']?([A-Za-zА-Яа-я_][\wА-Яа-я-]*)[`\"']?",
        r"(?:до|в)\s+[`\"']?([A-Za-z_][\w-]*)[`\"']?",
    ]
    matches: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if match.group(1) in columns:
                matches.append(match.group(1))
    if matches:
        return matches[-1]

    empty_columns = [
        column.name
        for column in profile.first_sheet.columns
        if column.non_null_count == 0 or column.null_count > 0
    ]
    if empty_columns:
        return empty_columns[-1]

    if any(word in text.lower() for word in ["distance", "відстан", "расстоя"]):
        return "distance"
    if any(word in text.lower() for word in ["height", "висот", "elevation"]):
        return "height"
    if any(word in text.lower() for word in ["population", "населен", "популяц"]):
        return "population"
    if any(word in text.lower() for word in ["ceo", "chief executive", "директор", "керівник"]):
        return "ceo"
    return None


def _infer_lookup_attribute(text: str) -> tuple[str, str | None, str]:
    if any(word in text for word in ["height", "висот", "elevation"]):
        return "height", "meters", "number"
    if any(word in text for word in ["population", "населен", "популяц"]):
        return "population", "people", "number"
    if any(word in text for word in ["ceo", "chief executive", "директор", "керівник"]):
        return "ceo", None, "string"
    if any(word in text for word in ["date", "дата", "founded", "засн"]):
        return "date", None, "date"
    return "fact", None, "string"


def _entity_columns_for_lookup(columns: list[str]) -> list[str]:
    preferred = [
        "Mountain",
        "Company",
        "Name",
        "City",
        "Country",
        "Entity",
        "Product",
    ]
    entity_columns = [column for column in preferred if column in columns]
    if entity_columns:
        return entity_columns[:2]
    return columns[:2]


logger = logging.getLogger(__name__)


async def _llm_build_task_plan(task_description: str, profile: WorkbookProfile) -> TaskPlan | None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return None

    sheet = profile.first_sheet
    columns_info = [
        {
            "name": col.name,
            "dtype": col.dtype,
            "null_count": col.null_count,
            "sample_values": col.sample_values
        }
        for col in sheet.columns
    ]

    prompt = {
        "task_description": task_description,
        "workbook_profile": {
            "sheet_name": sheet.name,
            "row_count": sheet.row_count,
            "columns": columns_info,
            "sample_rows": sheet.sample_rows[:3]
        },
        "routing_choices": ["TABLE_CALC", "WEB_ENRICH", "HYBRID", "CLARIFICATION_REQUIRED", "UNSUPPORTED"],
        "dsl_types": ["formula", "group_share", "lookup", "distance"],
        "instruction": (
            "Design a task plan to fulfill the task_description using the workbook_profile. "
            "Select the best route name and create a list of DSL operations to execute. "
            "If you generate a formula DSL operation, make sure it is safe. "
            "If column names contain spaces or special characters, wrap them in col('Column Name') in the expression. "
            "For example, col('Sales Amount') + col('Tax')."
        ),
        "output_schema": {
            "route": "TABLE_CALC|WEB_ENRICH|HYBRID|CLARIFICATION_REQUIRED|UNSUPPORTED",
            "reason": "explanation of route selection",
            "operation": "formula|group_share|lookup|distance|clarification|unsupported",
            "target_column": "name of target column to enrich",
            "source_columns": ["list of source columns used"],
            "unit": "optional unit like km, meters, people",
            "dsl": {
                "type": "formula|group_share|lookup|distance",
                "target_column": "name of target column",
                "expression": "optional calculation expression, e.g., col('A') + col('B')",
                "source_columns": ["list of source columns"],
                "entity_columns": ["list of entity columns for lookup/distance"],
                "attribute": "optional attribute name for lookup, e.g., height, population, ceo",
                "unit": "optional unit",
                "value_type": "number|string|date|boolean"
            },
            "clarification_question": "optional question if CLARIFICATION_REQUIRED",
            "warnings": ["any warnings or assumptions"]
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. Do not explain outside JSON.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 1500,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
        payload = json.loads(response.json()["choices"][0]["message"]["content"])

        route_decision = RouteDecision(
            route=payload.get("route", "UNSUPPORTED"),
            reason=payload.get("reason", "")
        )

        dsl_payload = payload.get("dsl")
        dsl_plan = None
        if dsl_payload:
            dsl_plan = DSLPlan(
                type=dsl_payload.get("type"),
                target_column=dsl_payload.get("target_column"),
                expression=dsl_payload.get("expression"),
                source_columns=dsl_payload.get("source_columns", []),
                entity_columns=dsl_payload.get("entity_columns", []),
                attribute=dsl_payload.get("attribute"),
                unit=dsl_payload.get("unit"),
                value_type=dsl_payload.get("value_type")
            )

        return TaskPlan(
            task_description=task_description,
            target_sheet=sheet.name,
            target_column=payload.get("target_column") or dsl_plan.target_column if dsl_plan else "enriched_value",
            route=route_decision,
            operation=payload.get("operation") or dsl_plan.type if dsl_plan else "unsupported",
            source_columns=payload.get("source_columns") or dsl_plan.source_columns if dsl_plan else [],
            unit=payload.get("unit") or dsl_plan.unit if dsl_plan else None,
            dsl=dsl_plan,
            operations=[dsl_plan] if dsl_plan else [],
            requires_approval=route_decision.route in {"HYBRID", "WEB_ENRICH", "CLARIFICATION_REQUIRED"},
            clarification_question=payload.get("clarification_question"),
            confidence=route_decision.confidence,
            warnings=payload.get("warnings", [])
        )
    except Exception as exc:
        logger.warning(f"LLM planner failed: {exc}")
        return None


def _build_rule_task_plan(task_description: str, profile: WorkbookProfile) -> TaskPlan:
    columns = _column_names(profile)
    target_column = _extract_target_column(task_description, profile, columns) or "enriched_value"
    route = route_task(task_description, profile, target_column)
    text = task_description.lower()
    warnings: list[str] = []

    if route.route == "HYBRID" and any(word in text for word in ["distance", "відстан", "расстоя"]):
        source_columns = ["Capital_From", "Country_From", "Capital_To", "Country_To"]
        missing = [column for column in source_columns if column not in columns]
        if missing:
            warnings.append(f"Missing expected distance columns: {', '.join(missing)}")
        dsl = DSLPlan(
            type="distance",
            target_column=target_column,
            source_columns=source_columns,
            expression="haversine_km(from_lat, from_lon, to_lat, to_lon)",
            unit="km",
            value_type="number",
        )
        return TaskPlan(
            task_description=task_description,
            target_sheet=profile.first_sheet.name,
            target_column=target_column,
            route=route,
            operation="distance",
            source_columns=source_columns,
            unit="km",
            dsl=dsl,
            operations=[dsl],
            requires_approval=True,
            warnings=warnings,
        )

    if route.route == "HYBRID" and any(word in text for word in ["population", "населен", "популяц"]):
        population_column = next(
            (column for column in columns if column.lower() == "population"),
            "Population",
        )
        sales_column = next(
            (column for column in columns if column.lower() in {"sales", "revenue"}),
            None,
        )
        entity_columns = [column for column in ["City", "Country"] if column in columns]
        if not entity_columns:
            entity_columns = _entity_columns_for_lookup(columns)
        lookup_dsl = DSLPlan(
            type="lookup",
            target_column=population_column,
            source_columns=entity_columns,
            entity_columns=entity_columns,
            attribute="population",
            unit="people",
            value_type="number",
        )
        operations = [lookup_dsl]
        source_columns = [*entity_columns]
        if sales_column:
            formula_dsl = DSLPlan(
                type="formula",
                target_column=target_column,
                source_columns=[sales_column, population_column],
                expression=f"div(col({sales_column!r}), col({population_column!r}))",
                value_type="number",
            )
            operations.append(formula_dsl)
            source_columns.extend([sales_column, population_column])
        else:
            warnings.append("Hybrid task needs a Sales or Revenue column for per-capita calculation.")

        return TaskPlan(
            task_description=task_description,
            target_sheet=profile.first_sheet.name,
            target_column=target_column,
            route=route,
            operation="lookup",
            source_columns=source_columns,
            unit=None,
            dsl=operations[0],
            operations=operations,
            requires_approval=True,
            warnings=warnings,
        )

    if route.route == "WEB_ENRICH":
        attribute, unit, value_type = _infer_lookup_attribute(text)
        source_columns = _entity_columns_for_lookup(columns)
        dsl = DSLPlan(
            type="lookup",
            target_column=target_column,
            source_columns=source_columns,
            entity_columns=source_columns,
            attribute=attribute,
            unit=unit,
            value_type=value_type,
        )
        return TaskPlan(
            task_description=task_description,
            target_sheet=profile.first_sheet.name,
            target_column=target_column,
            route=route,
            operation="lookup",
            source_columns=source_columns,
            unit=unit,
            dsl=dsl,
            operations=[dsl],
            requires_approval=True,
            warnings=warnings,
        )

    if route.route == "TABLE_CALC":
        normalized_columns = {column.lower(): column for column in columns}
        if any(word in text for word in ["share", "дол", "частк", "percent", "percentage"]):
            numeric_columns = [
                column.name
                for column in profile.first_sheet.columns
                if column.name != target_column and column.dtype in {"int64", "float64", "int", "float"}
            ]
            source_columns = numeric_columns[:1] or [column for column in columns if column != target_column][:1]
            if any(word in text for word in ["загаль", "overall", "total", "all sales"]):
                group_columns = []
            else:
                group_columns = [
                    column
                    for column in columns
                    if column not in source_columns and column != target_column
                ][:1]
            dsl = DSLPlan(
                type="group_share",
                target_column=target_column,
                source_columns=[*source_columns, *group_columns],
                expression="value / group_sum",
                value_type="number",
            )
            return TaskPlan(
                task_description=task_description,
                target_sheet=profile.first_sheet.name,
                target_column=target_column,
                route=route,
                operation="group_share",
                source_columns=dsl.source_columns,
                dsl=dsl,
                operations=[dsl],
                warnings=warnings,
            )

        if {"a", "b", "operation"}.issubset(normalized_columns) and target_column.lower() in {
            "value",
            "result",
            "результат",
        }:
            source_columns = [
                normalized_columns["a"],
                normalized_columns["b"],
                normalized_columns["operation"],
            ]
            return TaskPlan(
                task_description=task_description,
                target_sheet=profile.first_sheet.name,
                target_column=target_column,
                route=route,
                operation="formula",
                source_columns=source_columns,
                dsl=DSLPlan(
                    type="formula",
                    target_column=target_column,
                    source_columns=source_columns,
                    expression="apply_operation(A, B, Operation)",
                    value_type="number",
                ),
                operations=[
                    DSLPlan(
                        type="formula",
                        target_column=target_column,
                        source_columns=source_columns,
                        expression="apply_operation(A, B, Operation)",
                        value_type="number",
                    )
                ],
                warnings=warnings,
            )

        source_columns = [column for column in columns if column != target_column]
        expression = None
        if len(source_columns) >= 2 and any(
            word in text for word in ["a+b", "sum", "сума", "сум", "add", "добав", "додай"]
        ):
            def _col_expr(col_name: str) -> str:
                if re.match(r"^[A-Za-z_]\w*$", col_name):
                    return col_name
                return f"col({repr(col_name)})"
            expression = f"add({_col_expr(source_columns[0])}, {_col_expr(source_columns[1])})"
        if len(source_columns) >= 2 and any(
            word in text for word in ["minus", "subtract", "sub", "минус", "віднім", "марж", "margin"]
        ):
            def _col_expr(col_name: str) -> str:
                if re.match(r"^[A-Za-z_]\w*$", col_name):
                    return col_name
                return f"col({repr(col_name)})"
            expression = f"sub({_col_expr(source_columns[0])}, {_col_expr(source_columns[1])})"
        if expression is None:
            warnings.append("Could not derive a safe formula DSL from the task description.")
            return TaskPlan(
                task_description=task_description,
                target_sheet=profile.first_sheet.name,
                target_column=target_column,
                route=RouteDecision(
                    route="CLARIFICATION_REQUIRED",
                    reason="Formula task needs explicit source columns and expression.",
                ),
                operation="clarification",
                source_columns=source_columns,
                requires_approval=True,
                clarification_question=(
                    "Please specify the source columns and the formula to calculate the target column."
                ),
                warnings=warnings,
            )

        dsl = DSLPlan(
            type="formula",
            target_column=target_column,
            source_columns=source_columns[:2],
            expression=expression,
            value_type="number",
        )
        return TaskPlan(
            task_description=task_description,
            target_sheet=profile.first_sheet.name,
            target_column=target_column,
            route=route,
            operation="formula",
            source_columns=dsl.source_columns,
            dsl=dsl,
            operations=[dsl],
            warnings=warnings,
        )

    return TaskPlan(
        task_description=task_description,
        target_sheet=profile.first_sheet.name,
        target_column=target_column,
        route=route,
        operation="clarification" if route.route == "CLARIFICATION_REQUIRED" else "unsupported",
        source_columns=columns[:2],
        requires_approval=True,
        clarification_question=(
            "I could not reliably map this request to a supported calculation or enrichment. "
            "Please specify the source columns, target column, and the operation or fact to fill."
        )
        if route.route == "CLARIFICATION_REQUIRED"
        else None,
        warnings=warnings,
    )


def _estimate_external_calls(plan: TaskPlan, profile: WorkbookProfile) -> int:
    if plan.route.route not in {"WEB_ENRICH", "HYBRID"}:
        return 0

    sample_rows = profile.first_sheet.sample_rows
    row_count = profile.first_sheet.row_count
    if not sample_rows:
        multiplier = 2 if plan.operation == "distance" else 1
        return row_count * multiplier

    estimates: list[int] = []
    for operation in plan.operations:
        if operation.type == "lookup":
            entity_columns = operation.entity_columns or operation.source_columns[:2]
            keys = {
                "|".join(str(row.get(column) or "").strip() for column in entity_columns)
                for row in sample_rows
            }
            estimates.append(max(1, min(row_count, len(keys))))
        elif operation.type == "distance":
            source_columns = operation.source_columns or [
                "Capital_From",
                "Country_From",
                "Capital_To",
                "Country_To",
            ]
            endpoint_keys = set()
            for row in sample_rows:
                if len(source_columns) >= 2:
                    endpoint_keys.add(
                        "|".join(str(row.get(column) or "").strip() for column in source_columns[:2])
                    )
                if len(source_columns) >= 4:
                    endpoint_keys.add(
                        "|".join(str(row.get(column) or "").strip() for column in source_columns[2:4])
                    )
            estimates.append(max(2, min(row_count * 2, len(endpoint_keys) * 2)))
    return sum(estimates)


def _run_llm_planner(task_description: str, profile: WorkbookProfile) -> TaskPlan | None:
    if not get_settings().openrouter_api_key:
        return None
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(
                    lambda: asyncio.run(_llm_build_task_plan(task_description, profile))
                ).result()
        return asyncio.run(_llm_build_task_plan(task_description, profile))
    except Exception as exc:
        logger.warning("LLM planner fallback failed, falling back to rule-based: %s", exc)
        return None


def _finalize_plan(plan: TaskPlan, profile: WorkbookProfile) -> TaskPlan:
    estimated_external_calls = _estimate_external_calls(plan, profile)
    plan = plan.model_copy(
        update={
            "estimated_external_calls": estimated_external_calls,
            "confidence": plan.route.confidence,
        }
    )
    return plan_with_validation(plan, profile)


def build_task_plan(task_description: str, profile: WorkbookProfile) -> TaskPlan:
    rule_plan = _build_rule_task_plan(task_description, profile)
    validation = validate_task_plan(rule_plan, profile)
    rule_is_confident = (
        rule_plan.route.confidence >= 0.85
        and rule_plan.operation not in {"clarification", "unsupported"}
        and validation.ok
    )
    if rule_is_confident:
        return _finalize_plan(rule_plan, profile)

    llm_plan = _run_llm_planner(task_description, profile)
    if llm_plan is not None:
        finalized_llm_plan = _finalize_plan(llm_plan, profile)
        if finalized_llm_plan.operation != "clarification" or rule_plan.operation == "clarification":
            return finalized_llm_plan

    return _finalize_plan(rule_plan, profile)
