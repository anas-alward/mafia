"""Uniform error response helpers.

Ensures all error responses follow the Constitution §IV format:
{"error": "Human-readable message", "details": {"field": ["errors"]}}
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response


def api_error(message: str, status: int = 400, details: dict[str, Any] | None = None) -> Response:
    body: dict[str, Any] = {'error': message}
    if details:
        body['details'] = details
    return Response(body, status=status)


def api_validation_error(message: str, details: dict[str, list[str]]) -> Response:
    return api_error(message, status=400, details=details)
