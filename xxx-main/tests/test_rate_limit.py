import unittest

from auth_api.rate_limit import AuthenticationRateLimiter


class AuthenticationRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_identifier_limit_and_hashed_memory_keys(self) -> None:
        now = 100.0
        limiter = AuthenticationRateLimiter(
            key_secret="s" * 48,
            window_seconds=60,
            identifier_limit=1,
            ip_limit=5,
            clock=lambda: now,
        )
        identifier = "email:person@example.com"
        first = await limiter.consume(client_ip="203.0.113.1", identifier=identifier)
        second = await limiter.consume(client_ip="203.0.113.1", identifier=identifier)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.retry_after_seconds, 60)
        self.assertTrue(all(identifier not in key for key in limiter._counters))

        await limiter.clear_identifier(identifier)
        third = await limiter.consume(client_ip="203.0.113.1", identifier=identifier)
        self.assertTrue(third.allowed)

    async def test_counters_expire_without_external_storage(self) -> None:
        current_time = [100.0]
        limiter = AuthenticationRateLimiter(
            key_secret="s" * 48,
            window_seconds=10,
            identifier_limit=1,
            ip_limit=1,
            clock=lambda: current_time[0],
        )

        first = await limiter.consume(client_ip="203.0.113.1", identifier="person")
        blocked = await limiter.consume(client_ip="203.0.113.1", identifier="person")
        current_time[0] = 111.0
        after_expiry = await limiter.consume(
            client_ip="203.0.113.1", identifier="person"
        )

        self.assertTrue(first.allowed)
        self.assertFalse(blocked.allowed)
        self.assertTrue(after_expiry.allowed)


if __name__ == "__main__":
    unittest.main()
