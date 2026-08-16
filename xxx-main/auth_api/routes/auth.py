from __future__ import annotations

import logging

from anyio import CapacityLimiter, to_thread
from fastapi import APIRouter, Request, Response, status

from ..config import Settings
from ..errors import APIError
from ..identifier import resolve_identifier
from ..rate_limit import AuthenticationRateLimiter
from ..schemas import ErrorResponse, TokenRequest, TokenResponse
from ..security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    password_hash_needs_upgrade,
    verify_password,
)
from ..users import InMemoryUserRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

_INVALID_CREDENTIALS = "Invalid identifier or password"


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange user credentials for access and refresh tokens",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        422: {"model": ErrorResponse, "description": "Invalid request body"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def issue_token(
    payload: TokenRequest,
    request: Request,
    response: Response,
) -> TokenResponse:
    settings: Settings = request.app.state.settings
    rate_limiter: AuthenticationRateLimiter = request.app.state.auth_rate_limiter
    password_hash_limiter: CapacityLimiter = request.app.state.password_hash_limiter
    users: InMemoryUserRepository = request.app.state.auth_users

    resolved = resolve_identifier(payload.identifier, settings.default_phone_region)
    rate_limit_identifier = f"{resolved.kind.value}:{resolved.value}"
    client_ip = request.client.host if request.client else "unknown"

    decision = await rate_limiter.consume(
        client_ip=client_ip, identifier=rate_limit_identifier
    )
    if not decision.allowed:
        raise APIError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "TOO_MANY_ATTEMPTS",
            "Too many authentication attempts. Try again later",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    user = users.find_by_identifier(resolved)
    password = payload.password.get_secret_value()
    stored_hash = (
        user.password_hash
        if user is not None and user.password_hash.startswith("$argon2id$")
        else DUMMY_PASSWORD_HASH
    )
    password_is_valid = await to_thread.run_sync(
        verify_password, password, stored_hash, limiter=password_hash_limiter
    )

    # Keep this as one branch and one response for nonexistent, disabled, and
    # incorrect-password accounts to avoid exposing account state.
    if user is None or not user.is_active or not password_is_valid:
        raise APIError(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            _INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if password_hash_needs_upgrade(user.password_hash):
        logger.warning(
            "The Argon2id hash for authentication user %s should be regenerated",
            user.id,
        )

    refresh = create_refresh_token(settings)
    access_token = create_access_token(user.id, settings)

    await rate_limiter.clear_identifier(rate_limit_identifier)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.jwt_access_token_expire_seconds,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh.raw_token,
        max_age=settings.refresh_token_expire_days * 86_400,
        expires=refresh.expires_at,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )

    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh.raw_token,
        expiresIn=settings.jwt_access_token_expire_seconds,
    )
