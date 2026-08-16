import unittest
import uuid
from types import SimpleNamespace

from anyio import CapacityLimiter
from fastapi import Response
from starlette.requests import Request

from auth_api.config import Settings
from auth_api.errors import APIError
from auth_api.rate_limit import RateLimitDecision
from auth_api.routes.auth import issue_token
from auth_api.schemas import TokenRequest
from auth_api.security import hash_password
from auth_api.users import ConfiguredUser, InMemoryUserRepository


class FakeRateLimiter:
    def __init__(self) -> None:
        self.cleared: list[str] = []

    async def consume(self, **_kwargs: str) -> RateLimitDecision:
        return RateLimitDecision(allowed=True)

    async def clear_identifier(self, identifier: str) -> None:
        self.cleared.append(identifier)


class AuthRouteTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = Settings(
            jwt_secret="j" * 48,
            refresh_token_pepper="r" * 48,
            bot_enabled=False,
        )
        cls.password_hash = hash_password("valid-password")
        cls.user_id = uuid.uuid4()

    def users(self) -> InMemoryUserRepository:
        return InMemoryUserRepository(
            [
                ConfiguredUser(
                    id=self.user_id,
                    email="person@example.com",
                    username="person",
                    password_hash=self.password_hash,
                )
            ]
        )

    def request(
        self, limiter: FakeRateLimiter, users: InMemoryUserRepository
    ) -> Request:
        app = SimpleNamespace(
            state=SimpleNamespace(
                settings=self.settings,
                auth_rate_limiter=limiter,
                password_hash_limiter=CapacityLimiter(2),
                auth_users=users,
            )
        )
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/token",
                "headers": [],
                "client": ("203.0.113.10", 12345),
                "app": app,
            }
        )

    async def test_valid_credentials_issue_tokens_without_persistence(self) -> None:
        limiter = FakeRateLimiter()
        response = Response()
        users = self.users()

        result = await issue_token(
            TokenRequest(identifier="PERSON@example.com", password="valid-password"),
            self.request(limiter, users),
            response,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.tokenType, "Bearer")
        self.assertEqual(result.expiresIn, 3600)
        self.assertTrue(result.accessToken)
        self.assertTrue(result.refreshToken)
        self.assertEqual(limiter.cleared, ["email:person@example.com"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        set_cookie_headers = [
            value.decode("latin-1")
            for name, value in response.raw_headers
            if name.lower() == b"set-cookie"
        ]
        self.assertEqual(len(set_cookie_headers), 2)
        self.assertTrue(any("access_token=" in value for value in set_cookie_headers))
        self.assertTrue(any("refresh_token=" in value for value in set_cookie_headers))
        self.assertTrue(all("HttpOnly" in value for value in set_cookie_headers))
        self.assertTrue(all("Secure" in value for value in set_cookie_headers))

    async def test_unknown_and_wrong_password_have_same_error(self) -> None:
        errors: list[APIError] = []
        for identifier in ("unknown", "person"):
            with self.assertRaises(APIError) as caught:
                await issue_token(
                    TokenRequest(identifier=identifier, password="wrong-password"),
                    self.request(FakeRateLimiter(), self.users()),
                    Response(),
                )
            errors.append(caught.exception)

        self.assertEqual(
            [(error.status_code, error.code, error.message) for error in errors],
            [
                (401, "INVALID_CREDENTIALS", "Invalid identifier or password"),
                (401, "INVALID_CREDENTIALS", "Invalid identifier or password"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
