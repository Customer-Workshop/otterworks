"""Standard API error responses."""

from __future__ import annotations

from flask import Response, jsonify


def error_response(code: str, message: str, status: int) -> tuple[Response, int]:
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "status": status,
                }
            }
        ),
        status,
    )
