import unittest

from auth_api.rate_limit import AuthenticationRateLimiter


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.seen_keys: list[str] = []

    async def eval(self, _script: str, numkeys: int, *args: object) -> list[int]:
        keys = [str(value) for value in args[:numkeys]]
        self.seen_keys.extend(keys)
        result: list[int] = []
        for key in keys:
            self.counts[key] = self.counts.get(key, 0) + 1
            result.extend([self.counts[key], 60_000])
        return result

    async def delete(self, key: str) -> None:
        self.counts.pop(key, None)


class AuthenticationRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_identifier_limit_and_hashed_redis_keys(self) -> None:
        redis = FakeRedis()
        limiter = AuthenticationRateLimiter(
            redis,  # type: ignore[arg-type]
            key_secret="s" * 48,
            window_seconds=60,
            identifier_limit=1,
            ip_limit=5,
        )
        identifier = "email:person@example.com"
        first = await limiter.consume(client_ip="203.0.113.1", identifier=identifier)
        second = await limiter.consume(client_ip="203.0.113.1", identifier=identifier)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.retry_after_seconds, 60)
        self.assertTrue(all(identifier not in key for key in redis.seen_keys))

        await limiter.clear_identifier(identifier)
        third = await limiter.consume(client_ip="203.0.113.1", identifier=identifier)
        self.assertTrue(third.allowed)


if __name__ == "__main__":
    unittest.main()
