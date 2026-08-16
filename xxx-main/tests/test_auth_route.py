import unittest
import uuid
from types import SimpleNamespace

from anyio import CapacityLimiter
from fastapi import Response
from starlette.requests import Request

from auth_api.config import Settings
from auth_api.errors import APIError
from auth_api.models import User
from auth_api.rate_limit import RateLimitDecision
from auth_api.routes.auth import issue_token
from auth_api.schemas import TokenRequest
from auth_api.security import hash_password


class FakeResult:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def scalar_one_or_none(self) -> User | None:
        return self.user


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.added: list[object] = []
        self.committed = False

    async def execute(self, _query: object) -> FakeResult:
        return FakeResult(self.user)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


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
            database_url="postgresql://user:password@db/test",
            redis_url="redis://redis:6379/0",
            jwt_secret="j" * 48,
            refresh_token_pepper="r" * 48,
            bot_enabled=False,
        )
        cls.password_hash = hash_password("valid-password")

    def request(self, limiter: FakeRateLimiter) -> Request:
        app = SimpleNamespace(
            state=SimpleNamespace(
                settings=self.settings,
                auth_rate_limiter=limiter,
                password_hash_limiter=CapacityLimiter(2),
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

    async def test_valid_credentials_issue_and_persist_tokens(self) -> None:
        user = User(
            id=uuid.uuid4(),
            email_normalized="person@example.com",
            password_hash=self.password_hash,
            is_active=True,
        )
        session = FakeSession(user)
        limiter = FakeRateLimiter()
        response = Response()

        result = await issue_token(
            TokenRequest(identifier="PERSON@example.com", password="valid-password"),
            self.request(limiter),
            response,
            session,  # type: ignore[arg-type]
        )

        self.assertTrue(result.success)
        self.assertEqual(result.tokenType, "Bearer")
        self.assertEqual(result.expiresIn, 3600)
        self.assertTrue(result.accessToken)
        self.assertTrue(result.refreshToken)
        self.assertTrue(session.committed)
        self.assertEqual(len(session.added), 1)
        self.assertEqual(limiter.cleared, ["email:person@example.com"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_unknown_and_wrong_password_have_same_error(self) -> None:
        user = User(
            id=uuid.uuid4(),
            username_normalized="person",
            password_hash=self.password_hash,
            is_active=True,
        )
        errors: list[APIError] = []
        for stored_user in (None, user):
            with self.assertRaises(APIError) as caught:
                await issue_token(
                    TokenRequest(identifier="person", password="wrong-password"),
                    self.request(FakeRateLimiter()),
                    Response(),
                    FakeSession(stored_user),  # type: ignore[arg-type]
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
