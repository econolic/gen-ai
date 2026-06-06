import json

from starlette.requests import Request

from app.main import _error_code_for_status, _error_response


def _request_with_id(request_id: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/demo",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 123),
        }
    )
    request.state.request_id = request_id
    return request


def test_error_status_maps_to_codes():
    assert _error_code_for_status(400) == "VALIDATION_ERROR"
    assert _error_code_for_status(404) == "NOT_FOUND"
    assert _error_code_for_status(409) == "CONFLICT"
    assert _error_code_for_status(422) == "VALIDATION_ERROR"
    assert _error_code_for_status(429) == "RATE_LIMITED"
    assert _error_code_for_status(503) == "UPSTREAM_UNAVAILABLE"
    assert _error_code_for_status(500) == "UNKNOWN_ERROR"


def test_error_response_uses_envelope_and_request_id():
    response = _error_response(
        _request_with_id("req-unit"),
        status_code=404,
        code="NOT_FOUND",
        message="Run not found",
        recoverable=False,
    )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "req-unit"
    body = json.loads(response.body)
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Run not found"
    assert body["error"]["recoverable"] is False
    assert body["meta"]["request_id"] == "req-unit"
