import unittest
from datetime import datetime, timezone

import jwt

from auth_api.config import Settings
from auth_api.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = Settings(
            database_url="postgresql://user:password@db/test",
            redis_url="redis://redis:6379/0",
            jwt_secret="j" * 48,
            refresh_token_pepper="r" * 48,
            bot_enabled=False,
        )

    def test_argon2_hash_and_verify(self) -> None:
        encoded = hash_password("correct horse battery staple")
        self.assertTrue(encoded.startswith("$argon2id$"))
        self.assertTrue(verify_password("correct horse battery staple", encoded))
        self.assertFalse(verify_password("incorrect", encoded))

    def test_access_token_contains_required_claims(self) -> None:
        now = datetime(2026, 8, 16, tzinfo=timezone.utc)
        token = create_access_token("user-id", self.settings, now=now)
        claims = jwt.decode(
            token,
            self.settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=self.settings.jwt_audience,
            issuer=self.settings.jwt_issuer,
            options={"verify_exp": False},
        )
        self.assertEqual(claims["sub"], "user-id")
        self.assertEqual(claims["iat"], int(now.timestamp()))
        self.assertEqual(
            claims["exp"] - claims["iat"],
            self.settings.jwt_access_token_expire_seconds,
        )

    def test_refresh_token_is_opaque_and_only_hash_is_persistable(self) -> None:
        refresh = create_refresh_token(self.settings)
        self.assertGreaterEqual(len(refresh.raw_token), 64)
        self.assertNotEqual(refresh.raw_token, refresh.token_hash)
        self.assertEqual(len(refresh.token_hash), 64)
        self.assertEqual(
            refresh.token_hash,
            hash_refresh_token(refresh.raw_token, self.settings),
        )


if __name__ == "__main__":
    unittest.main()
