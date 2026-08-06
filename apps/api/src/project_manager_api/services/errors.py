from typing import Any


class ServiceError(RuntimeError):
    status_code = 400

    def __init__(self, detail: str | dict[str, Any]) -> None:
        self.detail = detail
        super().__init__(str(detail))


class NotFoundError(ServiceError):
    status_code = 404


class ForbiddenError(ServiceError):
    status_code = 403


class UnauthorizedError(ServiceError):
    status_code = 401


class ConfigurationError(ServiceError):
    status_code = 503


class ConflictError(ServiceError):
    status_code = 409


class PersistedConflictError(ConflictError):
    """A conflict whose diagnostic state must be committed before returning."""
