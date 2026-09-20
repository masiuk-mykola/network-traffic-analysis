import math
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema

BEARER_CHALLENGE = 'Bearer error="invalid_token"'

MAX_ECHO_DEPTH = 6
"""How deep a rejected request body is echoed back in a 422 ``input``."""

MAX_ECHO_ITEMS = 50
"""How many entries of a rejected list/mapping are echoed back in a 422 ``input``."""


class ErrorBody(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "description": (
                "Error envelope of every domain error. Extra keys carry machine-readable context."
            )
        },
    )

    detail: str = Field(description="Human-readable message.")
    code: str = Field(description="Stable snake_case error code.")


class ValidationIssue(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "One entry of FastAPI's default request-validation error list."
        }
    )

    loc: list[str | int]
    msg: str
    type: str
    ctx: dict[str, Any] | SkipJsonSchema[None] = None
    input: Any = None


class ValidationErrorBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "FastAPI's default 422 body: detail is a LIST here, unlike ErrorBody."
        }
    )

    detail: list[ValidationIssue]


class DomainError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        *,
        extra: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(f"{status} {code}: {detail}")
        self.status = status
        self.code = code
        self.detail = detail
        self.extra: dict[str, Any] = dict(extra or {})
        self.headers: dict[str, str] = dict(headers or {})

    def body(self) -> dict[str, Any]:
        return {**self.extra, "detail": self.detail, "code": self.code}

    def to_response(self) -> JSONResponse:
        return JSONResponse(self.body(), status_code=self.status, headers=self.headers or None)

    @classmethod
    def unauthorized(cls, code: str, detail: str) -> "DomainError":
        return cls(401, code, detail, headers={"WWW-Authenticate": BEARER_CHALLENGE})

    @classmethod
    def forbidden(cls, required: str) -> "DomainError":
        return cls(
            403,
            "forbidden",
            f"This action requires the '{required}' permission.",
            extra={"required": required},
        )

    @classmethod
    def forbidden_sensor(cls, sensor_id: str) -> "DomainError":
        return cls(
            403,
            "forbidden_sensor",
            f"You do not have access to sensor '{sensor_id}'.",
            extra={"sensor_id": sensor_id},
        )

    @classmethod
    def not_found(cls, code: str, detail: str) -> "DomainError":
        return cls(404, code, detail)

    @classmethod
    def rate_limited(
        cls, code: str, detail: str, retry_after_s: int, **extra: Any
    ) -> "DomainError":
        return cls(
            429,
            code,
            detail,
            extra=extra,
            headers={"Retry-After": str(max(1, int(retry_after_s)))},
        )

    @classmethod
    def unavailable(cls, code: str, detail: str, retry_after_s: int) -> "DomainError":
        return cls(503, code, detail, headers={"Retry-After": str(max(1, int(retry_after_s)))})


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # pragma: no cover - registered for DomainError only
        raise exc
    return exc.to_response()


def echo_safely(value: Any, depth: int = 0) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, bytes | bytearray):
        return bytes(value[:MAX_ECHO_ITEMS]).decode("utf-8", "replace")
    if depth >= MAX_ECHO_DEPTH:
        return "…"
    return _echo_container(value, depth)


def _echo_container(value: Any, depth: int) -> Any:
    if isinstance(value, Mapping):
        items = list(value.items())[:MAX_ECHO_ITEMS]
        return {str(key): echo_safely(item, depth + 1) for key, item in items}
    if isinstance(value, Sequence | set | frozenset):
        return [echo_safely(item, depth + 1) for item in list(value)[:MAX_ECHO_ITEMS]]
    return str(value)


async def _validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered for it only
        raise exc
    issues: list[dict[str, Any]] = []
    try:
        raw = list(exc.errors())
    except RecursionError:  # pragma: no cover - pydantic gave up describing the body
        raw = []
    for error in raw:
        issue: dict[str, Any] = {
            "type": str(error.get("type", "value_error")),
            "loc": [part if isinstance(part, int) else str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "Invalid input")),
            "input": echo_safely(error.get("input")),
        }
        if error.get("ctx") is not None:
            issue["ctx"] = echo_safely(error["ctx"])
        issues.append(issue)
    if not issues:
        issues = [
            {
                "type": "recursion_loop",
                "loc": ["body"],
                "msg": "The request body is nested too deeply to parse.",
                "input": None,
            }
        ]
    return JSONResponse({"detail": issues}, status_code=422)


async def _recursion_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "detail": "The request body is nested too deeply to parse.",
            "code": "body_too_deep",
        },
        status_code=422,
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(RecursionError, _recursion_error_handler)


_DESCRIPTIONS: dict[int, str] = {
    400: "Bad request",
    401: "Missing, expired, invalid or revoked credentials",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    410: "Gone",
    412: "Precondition failed",
    413: "Payload too large",
    415: "Unsupported media type",
    422: "Semantic validation error",
    428: "Precondition required",
    429: "Rate limited; honour Retry-After",
    503: "Temporarily unavailable; honour Retry-After",
}


def error_responses(*statuses: int, bearer: bool = True) -> dict[int | str, dict[str, Any]]:
    responses: dict[int | str, dict[str, Any]] = {}
    for status in statuses:
        entry: dict[str, Any] = {
            "model": (ErrorBody | ValidationErrorBody) if status == 422 else ErrorBody,
            "description": _DESCRIPTIONS.get(status, "Error"),
        }
        if status in (429, 503):
            entry["headers"] = {
                "Retry-After": {
                    "description": "Integer seconds (an HTTP-date on /v1/auth/login).",
                    "schema": {"type": "string"},
                }
            }
        if status == 401 and bearer:
            entry["headers"] = {
                "WWW-Authenticate": {
                    "description": "Bearer challenge (Bearer-authenticated routes).",
                    "schema": {"type": "string"},
                }
            }
        responses[status] = entry
    return responses


_ERROR_REF = {"$ref": "#/components/schemas/ErrorBody"}
_VALIDATION_REF = {"$ref": "#/components/schemas/ValidationErrorBody"}


def json_error_responses(*statuses: int, bearer: bool = True) -> dict[int | str, dict[str, Any]]:
    responses = error_responses(*statuses, bearer=bearer)
    for status, entry in responses.items():
        entry.pop("model", None)
        schema = {"anyOf": [_ERROR_REF, _VALIDATION_REF]} if status == 422 else _ERROR_REF
        entry["content"] = {"application/json": {"schema": schema}}
    return responses
