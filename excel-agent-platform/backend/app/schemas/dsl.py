from typing import Literal

from pydantic import BaseModel, Field, field_validator

DslType = Literal[
    "formula",
    "group_share",
    "lookup",
    "distance",
]
ValueType = Literal["number", "string", "date", "boolean"]

FORBIDDEN_TOKENS = (
    "import",
    "open(",
    "exec",
    "eval",
    "subprocess",
    "__",
    "lambda",
    "os.",
    "sys.",
)


class DSLPlan(BaseModel):
    type: DslType
    target_column: str
    expression: str | None = None
    source_columns: list[str] = Field(default_factory=list)
    entity_columns: list[str] = Field(default_factory=list)
    attribute: str | None = None
    unit: str | None = None
    value_type: ValueType | None = None

    @field_validator("expression")
    @classmethod
    def reject_unsafe_expression(cls, value: str | None) -> str | None:
        if value is None:
            return value
        lowered = value.lower()
        for token in FORBIDDEN_TOKENS:
            if token in lowered:
                raise ValueError(f"Unsafe DSL token is not allowed: {token}")
        return value
