import unittest

from auth_api.identifier import IdentifierKind, resolve_identifier


class ResolveIdentifierTests(unittest.TestCase):
    def test_resolves_and_normalizes_email(self) -> None:
        result = resolve_identifier("  Person@Example.COM ")
        self.assertEqual(result.kind, IdentifierKind.EMAIL)
        self.assertEqual(result.value, "person@example.com")

    def test_resolves_phone_to_e164(self) -> None:
        result = resolve_identifier("+1 (415) 555-2671")
        self.assertEqual(result.kind, IdentifierKind.PHONE)
        self.assertEqual(result.value, "+14155552671")

    def test_resolves_case_insensitive_username(self) -> None:
        result = resolve_identifier("  MyUser  ")
        self.assertEqual(result.kind, IdentifierKind.USERNAME)
        self.assertEqual(result.value, "myuser")

    def test_invalid_email_shaped_value_stays_email_for_uniform_failure(self) -> None:
        result = resolve_identifier("not-an-email@")
        self.assertEqual(result.kind, IdentifierKind.EMAIL)
        self.assertEqual(result.value, "not-an-email@")


if __name__ == "__main__":
    unittest.main()
