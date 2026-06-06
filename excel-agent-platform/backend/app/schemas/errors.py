from typing import Any, Literal

from pydantic import BaseModel, Field

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "PERMISSION_DENIED",
    "RATE_LIMITED",
    "TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "BUSINESS_RULE_VIOLATION",
    "CONFLICT",
    "UNKNOWN_ERROR",
]


class ToolError(BaseModel):
    code: ErrorCode
    message: str
    recoverable: bool = True
    next_action: str | None = None


class ToolMeta(BaseModel):
    request_id: str | None = None
    latency_ms: int | None = None
    source: str | None = None
    cached: bool = False


class ToolEnvelope(BaseModel):
    ok: bool
    data: Any = None
    error: ToolError | None = None
    meta: ToolMeta = Field(default_factory=ToolMeta)

    @classmethod
    def success(cls, data: Any, source: str | None = None, cached: bool = False) -> "ToolEnvelope":
        return cls(ok=True, data=data, meta=ToolMeta(source=source, cached=cached))

    @classmethod
    def failure(
        cls,
        code: ErrorCode,
        message: str,
        *,
        recoverable: bool = True,
        next_action: str | None = None,
        source: str | None = None,
    ) -> "ToolEnvelope":
        return cls(
            ok=False,
            data=None,
            error=ToolError(
                code=code,
                message=message,
                recoverable=recoverable,
                next_action=next_action,
            ),
            meta=ToolMeta(source=source),
        )
