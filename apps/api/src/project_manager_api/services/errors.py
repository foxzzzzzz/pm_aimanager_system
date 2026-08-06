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


class ConflictError(ServiceError):
    status_code = 409
