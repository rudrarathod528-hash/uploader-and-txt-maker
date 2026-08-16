from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import Settings


PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# A real Argon2id hash used when the account does not exist. Running the same
# expensive verification path for unknown users reduces username-enumeration
# and timing side channels. This is intentionally not a usable credential.
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$OBeZ9poTD9x43iLJet1kvA$"
    "IGQy0HwKrZ8G/uIklhOiTPeB8YulP04fkf/LBUFbihc"
)


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    raw_token: str
    token_hash: str
    expires_at: datetime


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_hash_needs_upgrade(encoded_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return False


def create_access_token(
    subject: uuid.UUID | str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=settings.jwt_access_token_expire_seconds)
    claims = {
        "sub": str(subject),
        "iat": issued_at,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        headers={"typ": "JWT"},
    )


def hash_refresh_token(raw_token: str, settings: Settings) -> str:
    return hmac.new(
        settings.refresh_token_pepper.get_secret_value().encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_refresh_token(
    settings: Settings, *, now: datetime | None = None
) -> IssuedRefreshToken:
    issued_at = now or datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(48)
    return IssuedRefreshToken(
        raw_token=raw_token,
        token_hash=hash_refresh_token(raw_token, settings),
        expires_at=issued_at + timedelta(days=settings.refresh_token_expire_days),
    )
