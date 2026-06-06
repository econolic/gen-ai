from app.schemas.errors import ToolEnvelope

ERROR_RESPONSES = {
    400: {"model": ToolEnvelope, "description": "Bad request error envelope"},
    401: {"model": ToolEnvelope, "description": "Authentication error envelope"},
    403: {"model": ToolEnvelope, "description": "Permission error envelope"},
    404: {"model": ToolEnvelope, "description": "Not found error envelope"},
    409: {"model": ToolEnvelope, "description": "Run lifecycle conflict error envelope"},
    413: {"model": ToolEnvelope, "description": "Gateway payload too large error envelope"},
    422: {"model": ToolEnvelope, "description": "Validation error envelope"},
    429: {"model": ToolEnvelope, "description": "Rate limit error envelope"},
    500: {"model": ToolEnvelope, "description": "Internal server error envelope"},
    503: {"model": ToolEnvelope, "description": "Upstream unavailable error envelope"},
}
