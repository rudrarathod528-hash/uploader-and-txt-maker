from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
import uuid

from email_validator import EmailNotValidError, validate_email

from .identifier import IdentifierKind, normalize_username, resolve_identifier
from .security import hash_password
from .users import ConfiguredUser, InMemoryUserRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate environment configuration for an authentication user"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser(
        "generate-user", help="print one AUTH_API_USERS JSON object"
    )
    generate.add_argument("--id", type=uuid.UUID)
    generate.add_argument("--email")
    generate.add_argument("--phone")
    generate.add_argument("--username")
    generate.add_argument(
        "--phone-region",
        default=os.getenv("DEFAULT_PHONE_REGION", "IN"),
        help="region used for a phone number without a country code (default: IN)",
    )
    generate.add_argument(
        "--password-env",
        metavar="VARIABLE",
        help="read the password from this environment variable instead of prompting",
    )
    generate.add_argument("--inactive", action="store_true")
    subparsers.add_parser(
        "generate-secrets",
        help="generate JWT_SECRET and REFRESH_TOKEN_PEPPER values",
    )
    return parser


def _read_password(environment_variable: str | None) -> str:
    if environment_variable:
        password = os.getenv(environment_variable)
        if password is None:
            raise ValueError(f"Environment variable {environment_variable} is not set")
    else:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match")
    if not 8 <= len(password) <= 1024:
        raise ValueError("Password must be between 8 and 1024 characters")
    return password


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    try:
        return validate_email(
            email.strip(), check_deliverability=False
        ).normalized.casefold()
    except EmailNotValidError as exc:
        raise ValueError(f"Invalid email address: {exc}") from exc


def _normalize_phone(phone: str | None, region: str) -> str | None:
    if phone is None:
        return None
    resolved = resolve_identifier(phone, region)
    if resolved.kind is not IdentifierKind.PHONE:
        raise ValueError("Invalid phone number")
    return resolved.value


def _normalize_user(username: str | None, region: str) -> str | None:
    if username is None:
        return None
    normalized = normalize_username(username)
    if not 1 <= len(normalized) <= 64 or "@" in normalized:
        raise ValueError("Username must be 1-64 characters and cannot contain @")
    if resolve_identifier(normalized, region).kind is not IdentifierKind.USERNAME:
        raise ValueError("Username cannot be a valid email address or phone number")
    return normalized


def _generate_user(args: argparse.Namespace) -> None:
    email = _normalize_email(args.email)
    phone = _normalize_phone(args.phone, args.phone_region)
    username = _normalize_user(args.username, args.phone_region)
    if not any((email, phone, username)):
        raise ValueError("Provide at least one of --email, --phone, or --username")

    account_id = args.id or uuid.uuid4()
    password_hash = hash_password(_read_password(args.password_env))
    configured = ConfiguredUser(
        id=account_id,
        email=email,
        phone=phone,
        username=username,
        password_hash=password_hash,
        is_active=not args.inactive,
    )
    InMemoryUserRepository([configured], args.phone_region)

    print(
        json.dumps(
            {
                "id": str(account_id),
                "email": email,
                "phone": phone,
                "username": username,
                "password_hash": password_hash,
                "is_active": not args.inactive,
            },
            separators=(",", ":"),
        )
    )


def _generate_secrets() -> None:
    print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    print(f"REFRESH_TOKEN_PEPPER={secrets.token_urlsafe(48)}")


def main() -> None:
    args = _parser().parse_args()
    try:
        if args.command == "generate-user":
            _generate_user(args)
        elif args.command == "generate-secrets":
            _generate_secrets()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
