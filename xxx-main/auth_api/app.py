from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from anyio import CapacityLimiter
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .errors import APIError, api_error_handler, validation_error_handler
from .rate_limit import AuthenticationRateLimiter
from .routes.auth import router as auth_router
from .routes.health import router as health_router
from .users import InMemoryUserRepository

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        telegram_bot: Any | None = None

        application.state.settings = runtime_settings
        application.state.auth_users = InMemoryUserRepository(
            runtime_settings.auth_api_users,
            runtime_settings.default_phone_region,
        )
        application.state.password_hash_limiter = CapacityLimiter(
            runtime_settings.auth_password_hash_concurrency
        )
        application.state.auth_rate_limiter = AuthenticationRateLimiter(
            key_secret=runtime_settings.refresh_token_pepper.get_secret_value(),
            window_seconds=runtime_settings.auth_rate_limit_window_seconds,
            identifier_limit=runtime_settings.auth_rate_limit_per_identifier,
            ip_limit=runtime_settings.auth_rate_limit_per_ip,
        )

        logger.info(
            "Loaded %d authentication user(s)",
            application.state.auth_users.user_count,
        )

        try:
            if runtime_settings.bot_enabled:
                from main import bot

                telegram_bot = bot
                await telegram_bot.start()
                logger.info("Telegram bot started")

            yield
        finally:
            if telegram_bot is not None and telegram_bot.is_connected:
                await telegram_bot.stop()
                logger.info("Telegram bot stopped")

    application = FastAPI(
        title="Uploader Authentication API",
        version="2.0.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    application.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(  # type: ignore[arg-type]
        RequestValidationError, validation_error_handler
    )

    if runtime_settings.allowed_cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=runtime_settings.allowed_cors_origins,
            allow_credentials=False,
            allow_methods=["POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    application.include_router(health_router)
    application.include_router(auth_router)
    return application


app = create_app()
