"""Uniform error response helpers.

Ensures all error responses follow the format:
{"error": "Human-readable message", "errors": {"field": ["errors"]}}
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_error(
    message: str,
    status: int = 400,
    errors: dict[str, Any] | None = None,
) -> Response:
    body: dict[str, Any] = {'error': message}
    if errors:
        body['errors'] = errors
    return Response(body, status=status)


def api_validation_error(message: str, errors: dict[str, list[str]]) -> Response:
    return api_error(message, status=400, errors=errors)


def global_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler wrapping all unhandled exceptions.

    Formats 400/validation errors as {"error": "...", "errors": {...}}.
    Delegates to DRF's default handler first, then normalizes the format.
    """
    response = exception_handler(exc, context)

    if response is not None and isinstance(response.data, dict):
        data = dict(response.data)
        detail = data.pop('detail', None)
        errors = data if data else None
        message = str(detail) if detail else str(exc)
        return api_error(message, status=response.status_code, errors=errors)

    return response
