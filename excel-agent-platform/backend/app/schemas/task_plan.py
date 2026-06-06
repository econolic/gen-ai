from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.dsl import DSLPlan

RouteName = Literal[
    "TABLE_CALC",
    "WEB_ENRICH",
    "HYBRID",
    "CLARIFICATION_REQUIRED",
    "UNSUPPORTED",
]


class RouteDecision(BaseModel):
    route: RouteName
    reason: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    freshness_required: bool = False


class TaskPlan(BaseModel):
    task_description: str
    target_sheet: str
    target_column: str
    route: RouteDecision
    operation: Literal[
        "formula",
        "group_share",
        "lookup",
        "distance",
        "clarification",
        "unsupported",
    ]
    source_columns: list[str] = Field(default_factory=list)
    unit: str | None = None
    dsl: DSLPlan | None = None
    operations: list[DSLPlan] = Field(default_factory=list)
    requires_approval: bool = False
    clarification_question: str | None = None
    estimated_external_calls: int = Field(default=0, ge=0)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def keep_legacy_dsl_aliases(self) -> "TaskPlan":
        if not self.operations and self.dsl is not None:
            self.operations = [self.dsl]
        if self.operations and self.dsl is None:
            self.dsl = self.operations[0]
        return self
