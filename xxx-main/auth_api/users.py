from __future__ import annotations

import uuid
from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from .identifier import (
    IdentifierKind,
    ResolvedIdentifier,
    normalize_username,
    resolve_identifier,
)


class ConfiguredUser(BaseModel):
    """A login account supplied through the AUTH_API_USERS environment variable."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str | None = None
    phone: str | None = None
    username: str | None = None
    password_hash: SecretStr
    is_active: bool = True

    @model_validator(mode="after")
    def validate_account(self) -> "ConfiguredUser":
        if not any((self.email, self.phone, self.username)):
            raise ValueError("At least one of email, phone, or username is required")
        if not self.password_hash.get_secret_value().startswith("$argon2id$"):
            raise ValueError("password_hash must be an Argon2id hash")
        return self


@dataclass(frozen=True, slots=True)
class User:
    id: uuid.UUID
    password_hash: str
    is_active: bool


class InMemoryUserRepository:
    """Immutable, normalized user index built from environment configuration."""

    def __init__(
        self,
        configured_users: list[ConfiguredUser],
        default_phone_region: str = "IN",
    ) -> None:
        self._users: dict[tuple[IdentifierKind, str], User] = {}
        self._user_count = len(configured_users)
        user_ids: set[uuid.UUID] = set()

        for configured in configured_users:
            if configured.id in user_ids:
                raise ValueError(f"Duplicate configured user id: {configured.id}")
            user_ids.add(configured.id)

            user = User(
                id=configured.id,
                password_hash=configured.password_hash.get_secret_value(),
                is_active=configured.is_active,
            )
            identifiers = self._normalized_identifiers(configured, default_phone_region)
            for identifier in identifiers:
                key = (identifier.kind, identifier.value)
                if key in self._users:
                    raise ValueError(
                        f"Duplicate configured {identifier.kind.value}: {identifier.value}"
                    )
                self._users[key] = user

    @property
    def user_count(self) -> int:
        return self._user_count

    def find_by_identifier(self, identifier: ResolvedIdentifier) -> User | None:
        return self._users.get((identifier.kind, identifier.value))

    @staticmethod
    def _normalized_identifiers(
        configured: ConfiguredUser, default_phone_region: str
    ) -> list[ResolvedIdentifier]:
        identifiers: list[ResolvedIdentifier] = []

        if configured.email is not None:
            try:
                email = validate_email(
                    configured.email.strip(), check_deliverability=False
                ).normalized.casefold()
            except EmailNotValidError as exc:
                raise ValueError(f"Invalid configured email address: {exc}") from exc
            identifiers.append(ResolvedIdentifier(IdentifierKind.EMAIL, email))

        if configured.phone is not None:
            phone = resolve_identifier(configured.phone, default_phone_region)
            if phone.kind is not IdentifierKind.PHONE:
                raise ValueError(f"Invalid configured phone number: {configured.phone}")
            identifiers.append(phone)

        if configured.username is not None:
            username = normalize_username(configured.username)
            if not 1 <= len(username) <= 64 or "@" in username:
                raise ValueError(
                    "Configured username must be 1-64 characters and cannot contain @"
                )
            resolved = resolve_identifier(username, default_phone_region)
            if resolved.kind is not IdentifierKind.USERNAME:
                raise ValueError(
                    "Configured username cannot be a valid email address or phone number"
                )
            identifiers.append(resolved)

        return identifiers
