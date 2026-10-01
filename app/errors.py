"""Application exception hierarchy and uniform error representations."""

from typing import Any


class AppError(Exception):
    """Base application exception."""

    def __init__(self, message: str, code: str = "bad_request", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(AppError):
    """Resource not found error."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="not_found", status_code=404)


class ValidationError(AppError):
    """Business validation or bad input error."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message=message, code="validation_error", status_code=422)
        self.details = details


class DatabaseError(AppError):
    """Database operation failure."""

    def __init__(self, message: str = "Database operation failed") -> None:
        super().__init__(message=message, code="database_error", status_code=500)
