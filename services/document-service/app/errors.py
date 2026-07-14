"""Standard API error responses."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def error_code(status: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }.get(status, "HTTP_ERROR")


def error_response(status: int, message: str, code: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code or error_code(status),
                "message": message,
                "status": status,
            }
        },
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(exc.status_code, str(exc.detail))


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    ]
    return error_response(422, ", ".join(messages), "VALIDATION_ERROR")


async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(500, "Internal server error", "INTERNAL_ERROR")
