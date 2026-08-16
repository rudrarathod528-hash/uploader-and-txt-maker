import json
import unittest

from fastapi.exceptions import RequestValidationError

from auth_api.errors import validation_error_handler


class ValidationErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_response_does_not_reflect_input(self) -> None:
        secret_input = "password-that-must-not-be-reflected"
        error = RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("body", "password"),
                    "msg": "too long",
                    "input": secret_input,
                }
            ]
        )
        response = await validation_error_handler(None, error)  # type: ignore[arg-type]
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["error"]["code"], "INVALID_REQUEST")
        self.assertNotIn(secret_input, response.body.decode())


if __name__ == "__main__":
    unittest.main()
