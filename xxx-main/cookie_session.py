from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests


class CookieSessionError(RuntimeError):
    """Base exception for cookie-session operations."""


class CookieSessionConfigurationError(CookieSessionError):
    pass


class CookieAuthenticationError(CookieSessionError):
    pass


class UnauthenticatedSessionError(CookieSessionError):
    pass


class EmptyCookieSessionError(CookieSessionError):
    pass


@dataclass(frozen=True, slots=True)
class CookieAuthConfig:
    url: str | None
    identifier: str | None
    password: str | None
    identifier_field: str = "identifier"
    password_field: str = "password"
    request_format: str = "json"
    timeout_seconds: float = 30.0
    extra_fields: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_environment(cls) -> "CookieAuthConfig":
        return cls(
            url=_optional_environment("COOKIE_AUTH_URL"),
            identifier=_optional_environment("COOKIE_AUTH_IDENTIFIER"),
            password=_optional_environment("COOKIE_AUTH_PASSWORD"),
            identifier_field=os.getenv("COOKIE_AUTH_IDENTIFIER_FIELD", "username").strip(),
            password_field=os.getenv("COOKIE_AUTH_PASSWORD_FIELD", "password").strip(),
            request_format=os.getenv("COOKIE_AUTH_REQUEST_FORMAT", "json")
            .strip()
            .lower(),
            timeout_seconds=_timeout_from_environment(),
            extra_fields=_json_object_from_environment("COOKIE_AUTH_EXTRA_FIELDS"),
            headers=_string_object_from_environment("COOKIE_AUTH_HEADERS"),
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("COOKIE_AUTH_URL", self.url),
                ("COOKIE_AUTH_IDENTIFIER", self.identifier),
                ("COOKIE_AUTH_PASSWORD", self.password),
            )
            if not value
        ]
        if missing:
            raise CookieSessionConfigurationError(
                f"Cookie authentication is not configured: missing {', '.join(missing)}"
            )

        parsed_url = urlparse(self.url or "")
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise CookieSessionConfigurationError(
                "COOKIE_AUTH_URL must be an absolute HTTP or HTTPS URL"
            )
        loopback_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed_url.scheme != "https" and parsed_url.hostname not in loopback_hosts:
            raise CookieSessionConfigurationError(
                "COOKIE_AUTH_URL must use HTTPS unless it targets a loopback host"
            )
        if not self.identifier_field or not self.password_field:
            raise CookieSessionConfigurationError(
                "Cookie authentication field names cannot be empty"
            )
        if self.identifier_field == self.password_field:
            raise CookieSessionConfigurationError(
                "Cookie identifier and password field names must be different"
            )
        if self.request_format not in {"json", "form"}:
            raise CookieSessionConfigurationError(
                "COOKIE_AUTH_REQUEST_FORMAT must be either json or form"
            )
        if not 1 <= self.timeout_seconds <= 120:
            raise CookieSessionConfigurationError(
                "COOKIE_AUTH_TIMEOUT_SECONDS must be between 1 and 120"
            )
        reserved_fields = {self.identifier_field, self.password_field}
        if reserved_fields.intersection(self.extra_fields):
            raise CookieSessionConfigurationError(
                "COOKIE_AUTH_EXTRA_FIELDS cannot replace credential fields"
            )

    def request_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            **self.extra_fields,
            self.identifier_field: self.identifier,
            self.password_field: self.password,
        }


def _optional_environment(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


def _timeout_from_environment() -> float:
    raw_value = os.getenv("COOKIE_AUTH_TIMEOUT_SECONDS", "30")
    try:
        return float(raw_value)
    except ValueError as exc:
        raise CookieSessionConfigurationError(
            "COOKIE_AUTH_TIMEOUT_SECONDS must be a number"
        ) from exc


def _json_object_from_environment(name: str) -> dict[str, Any]:
    raw_value = os.getenv(name, "{}").strip() or "{}"
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise CookieSessionConfigurationError(f"{name} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise CookieSessionConfigurationError(f"{name} must be a JSON object")
    return value


def _string_object_from_environment(name: str) -> dict[str, str]:
    value = _json_object_from_environment(name)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise CookieSessionConfigurationError(
            f"{name} keys and values must all be strings"
        )
    return value


class CookieSessionManager:
    """Thread-safe owner of one persistent requests.Session instance."""

    def __init__(
        self,
        config: CookieAuthConfig,
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.headers.setdefault(
            "User-Agent", "Uploader-and-TXT-Maker-Cookie-Session/1.0"
        )
        self._authenticated = False
        self._lock = threading.RLock()

    @property
    def is_authenticated(self) -> bool:
        with self._lock:
            return self._authenticated

    def authenticate(self) -> dict[str, str]:
        """Authenticate and return a copy of cookies captured from Set-Cookie headers."""
        payload = self._config.request_payload()

        with self._lock:
            self._session.cookies.clear()
            self._authenticated = False
            request_arguments: dict[str, Any] = {
                "headers": self._config.headers,
                "timeout": self._config.timeout_seconds,
                "allow_redirects": True,
            }
            if self._config.request_format == "json":
                request_arguments["json"] = payload
            else:
                request_arguments["data"] = payload

            try:
                response = self._session.post(
                    self._config.url or "", **request_arguments
                )
                response.raise_for_status()
            except requests.Timeout as exc:
                self._session.cookies.clear()
                raise CookieAuthenticationError(
                    "Authentication endpoint timed out"
                ) from exc
            except requests.RequestException as exc:
                self._session.cookies.clear()
                raise CookieAuthenticationError(
                    "Authentication endpoint rejected the request or is unavailable"
                ) from exc

            cookies = self._active_cookies()
            if not cookies:
                raise EmptyCookieSessionError(
                    "Authentication succeeded but the endpoint returned no cookies"
                )

            self._authenticated = True
            return cookies

    def get_cookies(self) -> dict[str, str]:
        """Return active cookies without exposing the mutable session cookie jar."""
        with self._lock:
            if not self._authenticated:
                raise UnauthenticatedSessionError(
                    "The session has not been authenticated"
                )
            cookies = self._active_cookies()
            if not cookies:
                self._authenticated = False
                raise EmptyCookieSessionError("The authenticated session has no active cookies")
            return cookies

    def _active_cookies(self) -> dict[str, str]:
        self._session.cookies.clear_expired_cookies()
        return dict(self._session.cookies.get_dict())
