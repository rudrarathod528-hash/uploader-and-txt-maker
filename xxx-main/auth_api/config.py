from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .users import ConfiguredUser


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    auth_api_users: list[ConfiguredUser] = Field(default_factory=list)

    jwt_secret: SecretStr
    refresh_token_pepper: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "uploader-and-txt-maker"
    jwt_audience: str = "uploader-api"
    jwt_access_token_expire_seconds: int = 3600
    refresh_token_expire_days: int = 30

    auth_rate_limit_window_seconds: int = 900
    auth_rate_limit_per_identifier: int = 10
    auth_rate_limit_per_ip: int = 50
    auth_password_hash_concurrency: int = 2
    default_phone_region: str = "IN"

    bot_enabled: bool = True
    cors_origins: str = ""

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if len(self.jwt_secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes")
        if len(self.refresh_token_pepper.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("REFRESH_TOKEN_PEPPER must contain at least 32 bytes")
        if self.jwt_algorithm != "HS256":
            raise ValueError("Only HS256 is supported by this deployment")
        if not 60 <= self.jwt_access_token_expire_seconds <= 86_400:
            raise ValueError(
                "JWT_ACCESS_TOKEN_EXPIRE_SECONDS must be between 60 and 86400"
            )
        if not 1 <= self.refresh_token_expire_days <= 365:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 365")
        if self.auth_rate_limit_window_seconds < 1:
            raise ValueError("AUTH_RATE_LIMIT_WINDOW_SECONDS must be positive")
        if self.auth_rate_limit_per_identifier < 1:
            raise ValueError("AUTH_RATE_LIMIT_PER_IDENTIFIER must be positive")
        if self.auth_rate_limit_per_ip < 1:
            raise ValueError("AUTH_RATE_LIMIT_PER_IP must be positive")
        if not 1 <= self.auth_password_hash_concurrency <= 16:
            raise ValueError("AUTH_PASSWORD_HASH_CONCURRENCY must be between 1 and 16")
        return self

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
