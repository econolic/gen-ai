from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

EvidenceKind = Literal[
    "offline_demo_seed",
    "seed_fact",
    "wikidata",
    "wikipedia",
    "serper",
    "calculation",
    "validation",
]


class Evidence(BaseModel):
    kind: EvidenceKind
    title: str
    url: str | None = None
    snippet: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactRequest(BaseModel):
    entity: str
    attribute: str
    unit: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


FactValueType = Literal["coordinates", "number", "string", "date"]


class CoordinatesValue(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return other == {"lat": self.lat, "lon": self.lon}
        return super().__eq__(other)


class NumberValue(BaseModel):
    value: float
    unit: str | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int | float):
            return self.value == float(other)
        return super().__eq__(other)


class StringValue(BaseModel):
    value: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.value == other
        return super().__eq__(other)


class DateValue(BaseModel):
    value: date | str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, date | str):
            return self.value == other
        return super().__eq__(other)


FactValue = CoordinatesValue | NumberValue | StringValue | DateValue


def _infer_value_type(payload: dict[str, Any]) -> FactValueType:
    request = payload.get("request") or {}
    if isinstance(request, FactRequest):
        request_data = request.model_dump()
    elif isinstance(request, dict):
        request_data = request
    else:
        request_data = {}
    context = request_data.get("context") or {}
    requested_type = payload.get("value_type") or context.get("value_type")
    if requested_type in {"coordinates", "number", "string", "date"}:
        return requested_type

    attribute = str(request_data.get("attribute") or "").lower()
    if attribute == "coordinates":
        return "coordinates"
    if attribute in {"height", "elevation", "population"}:
        return "number"
    if attribute in {"date", "founded"}:
        return "date"
    return "string"


class FactResult(BaseModel):
    request: FactRequest
    value_type: FactValueType = "string"
    value: FactValue | None = None
    unit: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_value(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        value_type = _infer_value_type(payload)
        payload["value_type"] = value_type
        value = payload.get("value")
        if value is None:
            return payload

        if value_type == "coordinates":
            if isinstance(value, CoordinatesValue):
                return payload
            if isinstance(value, dict):
                payload["value"] = {"lat": value.get("lat"), "lon": value.get("lon")}
            return payload

        if value_type == "number":
            if isinstance(value, NumberValue):
                return payload
            if isinstance(value, dict) and "value" in value:
                payload["value"] = {"value": value.get("value"), "unit": value.get("unit") or payload.get("unit")}
            else:
                payload["value"] = {"value": value, "unit": payload.get("unit")}
            return payload

        if value_type == "date":
            if isinstance(value, DateValue):
                return payload
            if isinstance(value, dict) and "value" in value:
                payload["value"] = {"value": value.get("value")}
            else:
                payload["value"] = {"value": value}
            return payload

        if isinstance(value, StringValue):
            return payload
        if isinstance(value, dict) and "value" in value:
            payload["value"] = {"value": str(value.get("value"))}
        else:
            payload["value"] = {"value": str(value)}
        return payload


def fact_value_to_python(value: FactValue | None) -> Any:
    if value is None:
        return None
    if isinstance(value, CoordinatesValue):
        return {"lat": value.lat, "lon": value.lon}
    if isinstance(value, NumberValue):
        return int(value.value) if value.value.is_integer() else value.value
    if isinstance(value, StringValue):
        return value.value
    if isinstance(value, DateValue):
        return value.value.isoformat() if isinstance(value.value, date) else value.value
    return value
