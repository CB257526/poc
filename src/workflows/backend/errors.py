"""统一错误响应：{detail, code, field_errors}。"""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        detail: str,
        *,
        code: str = "INTERNAL",
        status_code: int = 400,
        field_errors: Optional[dict[str, str]] = None,
    ):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code
        self.field_errors = field_errors


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    body: dict = {"detail": exc.detail, "code": exc.code}
    if exc.field_errors:
        body["field_errors"] = exc.field_errors
    return JSONResponse(status_code=exc.status_code, content=body)
