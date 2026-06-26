"""Uniform error response helpers.

All error responses follow the format:
{
  "message": "Human-readable message",
  "errors": [
    {"code": "error_code", "message": "Human-readable", "field": "optional"}
  ]
}
"""

from __future__ import annotations

from typing import Any, TypedDict

from rest_framework.response import Response
from rest_framework.views import exception_handler


class ErrorItem(TypedDict, total=False):
    code: str
    message: str
    field: str


def api_error(message: str, code: str = 'error', status: int = 400) -> Response:
    return Response({
        'message': message,
        'errors': [{'code': code, 'message': message}],
    }, status=status)


def api_validation_error(
    message: str,
    errors: dict[str, list[str]],
    code: str = 'invalid',
) -> Response:
    error_items: list[ErrorItem] = []
    for field, msgs in errors.items():
        for msg in msgs:
            error_items.append({
                'code': code,
                'message': str(msg),
                'field': field,
            })
    return Response({
        'message': message,
        'errors': error_items,
    }, status=400)


def global_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Response | None:
    """DRF exception handler wrapping all unhandled exceptions.

    Normalizes output to {"message": "...", "errors": [...]}.
    Delegates to DRF's default handler first, then reformats.
    """
    response = exception_handler(exc, context)

    if response is not None and isinstance(response.data, dict):
        data = dict(response.data)
        detail = data.pop('detail', None)
        message = str(detail) if detail else str(exc)

        error_items: list[ErrorItem] = []
        if data:
            for field, msgs in data.items():
                if isinstance(msgs, list):
                    for msg in msgs:
                        error_items.append({
                            'code': 'invalid',
                            'message': str(msg),
                            'field': field,
                        })
                else:
                    error_items.append({
                        'code': 'invalid',
                        'message': str(msgs),
                        'field': field,
                    })
        else:
            error_items.append({'code': 'error', 'message': message})

        return Response({
            'message': message,
            'errors': error_items,
        }, status=response.status_code)

    return response
