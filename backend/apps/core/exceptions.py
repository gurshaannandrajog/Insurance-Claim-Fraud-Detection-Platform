"""
Uniform error handling.

* Business-rule violations are raised from the service layer as `BusinessRuleError` (or a subclass)
  carrying a machine-readable `code` and an HTTP status. Views never build error responses by hand.
* Every API error has the shape: {"error": {"code": "...", "message": "...", "fields": {...}}}
* Unexpected exceptions are logged with a stack trace server-side and returned as a generic 500 —
  raw Python/Django tracebacks are never shown to users.
"""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class BusinessRuleError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_rule_violation"

    def __init__(self, message, code=None, status_code=None, fields=None, extra=None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        if status_code:
            self.status_code = status_code
        self.fields = fields or {}
        self.extra = extra or {}


class ConflictError(BusinessRuleError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class InvalidTransitionError(ConflictError):
    default_code = "invalid_status_transition"


class ForbiddenActionError(BusinessRuleError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"


class ServiceUnavailableError(BusinessRuleError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "service_unavailable"


def _body(code, message, fields=None, extra=None):
    payload = {"code": code, "message": message}
    if fields:
        payload["fields"] = fields
    if extra:
        payload.update(extra)
    return {"error": payload}


def _flatten(detail):
    if isinstance(detail, list):
        return [str(d) for d in detail]
    if isinstance(detail, dict):
        return {k: _flatten(v) for k, v in detail.items()}
    return [str(detail)]


def api_exception_handler(exc, context):
    if isinstance(exc, BusinessRuleError):
        return Response(_body(exc.code, exc.message, exc.fields, exc.extra), status=exc.status_code)

    if isinstance(exc, DjangoValidationError):
        fields = exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        return Response(_body("validation_error", "Please correct the highlighted fields.", fields),
                        status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, exceptions.ValidationError):
            detail = _flatten(exc.detail)
            fields = detail if isinstance(detail, dict) else {"non_field_errors": detail}
            response.data = _body("validation_error", "Please correct the highlighted fields.", fields)
        elif isinstance(exc, exceptions.NotAuthenticated):
            response.data = _body("not_authenticated", "Please sign in to continue.")
        elif isinstance(exc, exceptions.Throttled):
            response.data = _body("rate_limited", f"Too many requests. Try again in {int(exc.wait or 60)} seconds.")
        else:
            code = getattr(exc, "default_code", "error")
            response.data = _body(code, str(getattr(exc, "detail", "Request failed.")))
        return response

    if isinstance(exc, DatabaseError):
        logger.exception("Database error while handling %s", context.get("view"))
        return Response(_body("database_error", "A database error occurred. Please try again."),
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    logger.exception("Unhandled error in %s", context.get("view"))
    return Response(_body("server_error", "Something went wrong on our side. Please try again."),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
