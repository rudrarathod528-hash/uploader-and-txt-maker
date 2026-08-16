from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

import phonenumbers
from email_validator import EmailNotValidError, validate_email


class IdentifierKind(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    USERNAME = "username"


@dataclass(frozen=True, slots=True)
class ResolvedIdentifier:
    kind: IdentifierKind
    value: str


_PHONE_LIKE = re.compile(r"^[+0-9][0-9().\-\s]{6,}$")


def normalize_username(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


def resolve_identifier(
    identifier: str, default_phone_region: str = "IN"
) -> ResolvedIdentifier:
    """Resolve and normalize an email address, phone number, or username.

    Invalid email-looking values are still classified as email and normalized in a
    deterministic way. This lets the endpoint perform the same dummy password
    verification and return the same 401 response instead of exposing validation
    differences that could assist account discovery.
    """
    raw = unicodedata.normalize("NFKC", identifier.strip())

    if "@" in raw:
        try:
            normalized = validate_email(
                raw, check_deliverability=False
            ).normalized.casefold()
        except EmailNotValidError:
            normalized = raw.casefold()
        return ResolvedIdentifier(IdentifierKind.EMAIL, normalized)

    if _PHONE_LIKE.fullmatch(raw):
        try:
            parsed = phonenumbers.parse(raw, default_phone_region.upper())
            if phonenumbers.is_valid_number(parsed):
                normalized_phone = phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
                return ResolvedIdentifier(IdentifierKind.PHONE, normalized_phone)
        except phonenumbers.NumberParseException:
            pass

    return ResolvedIdentifier(IdentifierKind.USERNAME, normalize_username(raw))
