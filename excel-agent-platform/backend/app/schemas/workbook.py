from typing import Any

from pydantic import BaseModel, Field, field_validator


class ColumnProfile(BaseModel):
    name: str
    non_null_count: int
    null_count: int
    dtype: str
    sample_values: list[Any] = Field(default_factory=list)


class SheetProfile(BaseModel):
    name: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class WorkbookProfile(BaseModel):
    file_path: str
    sheets: list[SheetProfile]

    @field_validator("sheets")
    @classmethod
    def require_at_least_one_sheet(cls, value: list[SheetProfile]) -> list[SheetProfile]:
        if not value:
            raise ValueError("Workbook must contain at least one sheet")
        return value

    @property
    def first_sheet(self) -> SheetProfile:
        return self.sheets[0]
