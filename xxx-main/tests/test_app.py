import importlib
import os
import unittest
import uuid
from unittest.mock import patch

from auth_api.config import Settings
from auth_api.security import DUMMY_PASSWORD_HASH
from auth_api.users import ConfiguredUser


class ApplicationStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_starts_without_external_data_services(self) -> None:
        environment = {
            "AUTH_API_USERS": "[]",
            "JWT_SECRET": "j" * 48,
            "REFRESH_TOKEN_PEPPER": "r" * 48,
            "BOT_ENABLED": "false",
        }
        with patch.dict(os.environ, environment, clear=True):
            app_module = importlib.import_module("auth_api.app")

        settings = Settings(
            auth_api_users=[
                ConfiguredUser(
                    id=uuid.uuid4(),
                    username="person",
                    password_hash=DUMMY_PASSWORD_HASH,
                )
            ],
            jwt_secret="j" * 48,
            refresh_token_pepper="r" * 48,
            bot_enabled=False,
        )
        application = app_module.create_app(settings)

        async with application.router.lifespan_context(application):
            self.assertEqual(application.state.auth_users.user_count, 1)
            self.assertIsNotNone(application.state.auth_rate_limiter)


if __name__ == "__main__":
    unittest.main()
