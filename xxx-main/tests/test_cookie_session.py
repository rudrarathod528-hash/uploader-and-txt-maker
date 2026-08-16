import unittest

import requests

from cookie_session import (
    CookieAuthenticationError,
    CookieAuthConfig,
    CookieSessionConfigurationError,
    CookieSessionManager,
    EmptyCookieSessionError,
    UnauthenticatedSessionError,
)


class FakeResponse:
    def __init__(self, error: requests.RequestException | None = None) -> None:
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.failure: requests.RequestException | None = None
        self.set_cookie = True

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        if self.failure is not None:
            raise self.failure
        if self.set_cookie:
            self.cookies.set("sessionid", "active-session-value")
        return FakeResponse()


class CookieSessionManagerTests(unittest.TestCase):
    def config(self, **overrides: object) -> CookieAuthConfig:
        values: dict[str, object] = {
            "url": "https://accounts.example.com/login",
            "identifier": "person@example.com",
            "password": "strong-password",
        }
        values.update(overrides)
        return CookieAuthConfig(**values)  # type: ignore[arg-type]

    def test_authenticates_with_json_and_persists_cookies(self) -> None:
        session = FakeSession()
        manager = CookieSessionManager(
            self.config(extra_fields={"remember": True}),
            session=session,  # type: ignore[arg-type]
        )

        cookies = manager.authenticate()
        persisted = manager.get_cookies()

        self.assertEqual(cookies, {"sessionid": "active-session-value"})
        self.assertEqual(persisted, cookies)
        self.assertTrue(manager.is_authenticated)
        url, arguments = session.calls[0]
        self.assertEqual(url, "https://accounts.example.com/login")
        self.assertEqual(
            arguments["json"],
            {
                "remember": True,
                "identifier": "person@example.com",
                "password": "strong-password",
            },
        )
        self.assertNotIn("data", arguments)

    def test_supports_form_encoded_authentication(self) -> None:
        session = FakeSession()
        manager = CookieSessionManager(
            self.config(
                request_format="form",
                identifier_field="email",
                password_field="passcode",
            ),
            session=session,  # type: ignore[arg-type]
        )

        manager.authenticate()

        arguments = session.calls[0][1]
        self.assertEqual(
            arguments["data"],
            {"email": "person@example.com", "passcode": "strong-password"},
        )
        self.assertNotIn("json", arguments)

    def test_rejects_cookie_access_before_authentication(self) -> None:
        manager = CookieSessionManager(
            self.config(), session=FakeSession()  # type: ignore[arg-type]
        )

        with self.assertRaises(UnauthenticatedSessionError):
            manager.get_cookies()

    def test_rejects_success_response_without_cookies(self) -> None:
        session = FakeSession()
        session.set_cookie = False
        manager = CookieSessionManager(
            self.config(), session=session  # type: ignore[arg-type]
        )

        with self.assertRaises(EmptyCookieSessionError):
            manager.authenticate()
        self.assertFalse(manager.is_authenticated)

    def test_wraps_network_failures_without_exposing_credentials(self) -> None:
        session = FakeSession()
        session.failure = requests.ConnectionError("network unavailable")
        manager = CookieSessionManager(
            self.config(), session=session  # type: ignore[arg-type]
        )

        with self.assertRaises(CookieAuthenticationError) as caught:
            manager.authenticate()

        self.assertNotIn("strong-password", str(caught.exception))
        self.assertFalse(manager.is_authenticated)

    def test_requires_complete_configuration(self) -> None:
        config = self.config(url=None, password=None)

        with self.assertRaises(CookieSessionConfigurationError) as caught:
            config.validate()

        self.assertIn("COOKIE_AUTH_URL", str(caught.exception))
        self.assertIn("COOKIE_AUTH_PASSWORD", str(caught.exception))

    def test_rejects_cleartext_remote_authentication(self) -> None:
        config = self.config(url="http://accounts.example.com/login")

        with self.assertRaisesRegex(CookieSessionConfigurationError, "use HTTPS"):
            config.validate()


if __name__ == "__main__":
    unittest.main()
