import unittest

from sqlalchemy.dialects import postgresql

from auth_api.identifier import IdentifierKind, ResolvedIdentifier
from auth_api.repositories import user_lookup_query


class UserLookupQueryTests(unittest.TestCase):
    def test_each_identifier_uses_only_its_normalized_column(self) -> None:
        cases = {
            IdentifierKind.EMAIL: "email_normalized",
            IdentifierKind.PHONE: "phone_e164",
            IdentifierKind.USERNAME: "username_normalized",
        }
        all_columns = set(cases.values())

        for kind, expected_column in cases.items():
            with self.subTest(kind=kind):
                query = user_lookup_query(ResolvedIdentifier(kind, "private-value"))
                compiled = query.compile(dialect=postgresql.dialect())
                where_clause = str(compiled).split("WHERE", maxsplit=1)[1]
                self.assertIn(expected_column, where_clause)
                for other_column in all_columns - {expected_column}:
                    self.assertNotIn(other_column, where_clause)
                self.assertNotIn("private-value", str(compiled))
                self.assertIn("private-value", compiled.params.values())


if __name__ == "__main__":
    unittest.main()
