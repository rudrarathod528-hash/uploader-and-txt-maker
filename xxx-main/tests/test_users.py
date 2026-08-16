import json
import os
import unittest
import uuid
from unittest.mock import patch

from auth_api.config import Settings
from auth_api.identifier import resolve_identifier
from auth_api.security import DUMMY_PASSWORD_HASH
from auth_api.users import ConfiguredUser, InMemoryUserRepository


class InMemoryUserRepositoryTests(unittest.TestCase):
    def test_indexes_all_normalized_identifiers(self) -> None:
        user_id = uuid.uuid4()
        repository = InMemoryUserRepository(
            [
                ConfiguredUser(
                    id=user_id,
                    email="Person@Example.COM",
                    phone="+1 (415) 555-2671",
                    username="  MyUser  ",
                    password_hash=DUMMY_PASSWORD_HASH,
                )
            ]
        )

        for raw_identifier in (
            "person@example.com",
            "+14155552671",
            "myuser",
        ):
            with self.subTest(identifier=raw_identifier):
                user = repository.find_by_identifier(
                    resolve_identifier(raw_identifier)
                )
                self.assertIsNotNone(user)
                self.assertEqual(user.id, user_id)  # type: ignore[union-attr]

    def test_rejects_duplicate_normalized_identifier(self) -> None:
        users = [
            ConfiguredUser(
                id=uuid.uuid4(),
                email="person@example.com",
                password_hash=DUMMY_PASSWORD_HASH,
            ),
            ConfiguredUser(
                id=uuid.uuid4(),
                email="PERSON@example.com",
                password_hash=DUMMY_PASSWORD_HASH,
            ),
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate configured email"):
            InMemoryUserRepository(users)

    def test_rejects_duplicate_user_id(self) -> None:
        user_id = uuid.uuid4()
        users = [
            ConfiguredUser(
                id=user_id,
                username="first",
                password_hash=DUMMY_PASSWORD_HASH,
            ),
            ConfiguredUser(
                id=user_id,
                username="second",
                password_hash=DUMMY_PASSWORD_HASH,
            ),
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate configured user id"):
            InMemoryUserRepository(users)

    def test_settings_load_users_from_json_environment(self) -> None:
        user_id = uuid.uuid4()
        configured_users = json.dumps(
            [
                {
                    "id": str(user_id),
                    "username": "person",
                    "password_hash": DUMMY_PASSWORD_HASH,
                    "is_active": True,
                }
            ]
        )
        environment = {
            "AUTH_API_USERS": configured_users,
            "JWT_SECRET": "j" * 48,
            "REFRESH_TOKEN_PEPPER": "r" * 48,
            "BOT_ENABLED": "false",
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = Settings()

        self.assertEqual(len(settings.auth_api_users), 1)
        self.assertEqual(settings.auth_api_users[0].id, user_id)
        self.assertEqual(settings.auth_api_users[0].username, "person")

    def test_settings_require_no_external_service_url(self) -> None:
        settings = Settings(
            jwt_secret="j" * 48,
            refresh_token_pepper="r" * 48,
            bot_enabled=False,
        )

        self.assertEqual(settings.auth_api_users, [])


if __name__ == "__main__":
    unittest.main()
