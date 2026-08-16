from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .database import create_database_engine, create_session_factory
from .identifier import IdentifierKind, normalize_username, resolve_identifier
from .models import User
from .security import hash_password


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Authentication user administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-user", help="create a login user")
    create.add_argument("--email")
    create.add_argument("--phone")
    create.add_argument("--username")
    create.add_argument(
        "--password-env",
        metavar="VARIABLE",
        help="read the password from this environment variable instead of prompting",
    )
    create.add_argument("--inactive", action="store_true")
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


async def _create_user(args: argparse.Namespace) -> None:
    settings = get_settings()
    email = _normalize_email(args.email)
    phone = _normalize_phone(args.phone, settings.default_phone_region)
    username = _normalize_user(args.username, settings.default_phone_region)
    if not any((email, phone, username)):
        raise ValueError("Provide at least one of --email, --phone, or --username")

    password = _read_password(args.password_env)
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            session.add(
                User(
                    email_normalized=email,
                    phone_e164=phone,
                    username_normalized=username,
                    password_hash=hash_password(password),
                    is_active=not args.inactive,
                )
            )
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError(
                    "An email, phone, or username is already in use"
                ) from exc
    finally:
        await engine.dispose()

    print("User created successfully")


def main() -> None:
    args = _parser().parse_args()
    try:
        if args.command == "create-user":
            asyncio.run(_create_user(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
