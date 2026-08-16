from __future__ import annotations

import logging

from anyio import CapacityLimiter, to_thread
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..database import get_db_session
from ..errors import APIError
from ..identifier import resolve_identifier
from ..models import RefreshToken
from ..rate_limit import AuthenticationRateLimiter, RateLimiterUnavailable
from ..repositories import find_user_by_identifier
from ..schemas import ErrorResponse, TokenRequest, TokenResponse
from ..security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    hash_password,
    password_hash_needs_upgrade,
    verify_password,
)

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
        503: {"model": ErrorResponse, "description": "Authentication unavailable"},
    },
)
async def issue_token(
    payload: TokenRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    settings: Settings = request.app.state.settings
    rate_limiter: AuthenticationRateLimiter = request.app.state.auth_rate_limiter
    password_hash_limiter: CapacityLimiter = request.app.state.password_hash_limiter

    resolved = resolve_identifier(payload.identifier, settings.default_phone_region)
    rate_limit_identifier = f"{resolved.kind.value}:{resolved.value}"
    client_ip = request.client.host if request.client else "unknown"

    try:
        decision = await rate_limiter.consume(
            client_ip=client_ip, identifier=rate_limit_identifier
        )
    except RateLimiterUnavailable as exc:
        logger.error("Authentication rate limiter is unavailable", exc_info=exc)
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is temporarily unavailable",
            headers={"Retry-After": "5"},
        ) from exc

    if not decision.allowed:
        raise APIError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "TOO_MANY_ATTEMPTS",
            "Too many authentication attempts. Try again later",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    try:
        user = await find_user_by_identifier(session, resolved)
    except SQLAlchemyError as exc:
        logger.error("User lookup failed", exc_info=exc)
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is temporarily unavailable",
            headers={"Retry-After": "5"},
        ) from exc

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
        user.password_hash = await to_thread.run_sync(
            hash_password, password, limiter=password_hash_limiter
        )

    refresh = create_refresh_token(settings)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh.token_hash,
            expires_at=refresh.expires_at,
        )
    )
    access_token = create_access_token(user.id, settings)

    try:
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.error("Token persistence failed", exc_info=exc)
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is temporarily unavailable",
            headers={"Retry-After": "5"},
        ) from exc

    await rate_limiter.clear_identifier(rate_limit_identifier)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh.raw_token,
        expiresIn=settings.jwt_access_token_expire_seconds,
    )
