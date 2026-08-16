from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}
        super().__init__(message)


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        **exc.headers,
    }
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "success": False,
            "error": {"code": exc.code, "message": exc.message},
        },
    )


async def validation_error_handler(
    _: Request, __: RequestValidationError
) -> JSONResponse:
    """Return validation failures without reflecting password input to the client."""
    return JSONResponse(
        status_code=422,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        content={
            "success": False,
            "error": {
                "code": "INVALID_REQUEST",
                "message": "Request must include a valid identifier and password",
            },
        },
    )
