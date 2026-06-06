import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.runs import router as runs_router
from app.config import get_settings
from app.schemas.errors import ErrorCode, ToolEnvelope

logger = logging.getLogger(__name__)


def _error_code_for_status(status_code: int) -> ErrorCode:
    if status_code in {400, 422}:
        return "VALIDATION_ERROR"
    if status_code in {401, 403}:
        return "PERMISSION_DENIED"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code in {502, 503, 504}:
        return "UPSTREAM_UNAVAILABLE"
    return "UNKNOWN_ERROR"


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or uuid4())


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    recoverable: bool = True,
    next_action: str | None = None,
) -> JSONResponse:
    envelope = ToolEnvelope.failure(
        code,
        message,
        recoverable=recoverable,
        next_action=next_action,
        source="api",
    )
    envelope.meta.request_id = _request_id(request)
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={"X-Request-ID": envelope.meta.request_id or ""},
    )


def create_app() -> FastAPI:
    """Create the FastAPI application and expose OpenAPI/Swagger documentation."""

    settings = get_settings()
    app = FastAPI(
        title="Excel Agent Platform",
        version="0.1.0",
        summary="AI-assisted Excel data enrichment platform",
        description=(
            "Upload Excel workbooks, generate typed enrichment plans, run LangGraph "
            "orchestration, and download enriched workbooks plus evidence reports."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Excel Agent Platform"},
        license_info={"name": "MIT"},
        openapi_tags=[
            {
                "name": "health",
                "description": "Readiness endpoints for local and Docker smoke checks.",
            },
            {
                "name": "runs",
                "description": "Excel upload, enrichment lifecycle, preview, download, and reports.",
            },
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "api_request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "api_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _error_response(
            request,
            status_code=exc.status_code,
            code=_error_code_for_status(exc.status_code),
            message=detail,
            recoverable=exc.status_code >= 500,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            recoverable=True,
            next_action=str(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "api_unhandled_exception",
            extra={"request_id": _request_id(request), "path": request.url.path},
        )
        return _error_response(
            request,
            status_code=500,
            code="UNKNOWN_ERROR",
            message="Internal server error",
            recoverable=True,
        )

    app.include_router(health_router)
    app.include_router(runs_router)
    return app


app = create_app()
