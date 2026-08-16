from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError


_CONSUME_SCRIPT = """
local output = {}
local window_ms = tonumber(ARGV[1])
for _, key in ipairs(KEYS) do
    local count = redis.call('INCR', key)
    if count == 1 then
        redis.call('PEXPIRE', key, window_ms)
    end
    local ttl = redis.call('PTTL', key)
    table.insert(output, count)
    table.insert(output, ttl)
end
return output
"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiterUnavailable(RuntimeError):
    pass


class AuthenticationRateLimiter:
    """Redis-backed, process-safe fixed-window limiter for login attempts."""

    def __init__(
        self,
        redis: Redis,
        *,
        key_secret: str,
        window_seconds: int,
        identifier_limit: int,
        ip_limit: int,
    ) -> None:
        self._redis = redis
        self._key_secret = key_secret.encode("utf-8")
        self._window_seconds = window_seconds
        self._identifier_limit = identifier_limit
        self._ip_limit = ip_limit

    def _digest(self, scope: str, value: str) -> str:
        return hmac.new(
            self._key_secret,
            f"{scope}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _identifier_key(self, identifier: str) -> str:
        return f"auth-limit:id:{self._digest('identifier', identifier)}"

    async def consume(self, *, client_ip: str, identifier: str) -> RateLimitDecision:
        keys = [
            f"auth-limit:ip:{self._digest('ip', client_ip)}",
            self._identifier_key(identifier),
        ]
        try:
            raw = await self._redis.eval(  # type: ignore[misc]
                _CONSUME_SCRIPT,
                len(keys),
                *keys,
                str(self._window_seconds * 1000),
            )
        except RedisError as exc:
            raise RateLimiterUnavailable from exc

        ip_count, ip_ttl_ms, identifier_count, identifier_ttl_ms = map(int, raw)
        retry_after_ms = 0
        if ip_count > self._ip_limit:
            retry_after_ms = max(retry_after_ms, ip_ttl_ms)
        if identifier_count > self._identifier_limit:
            retry_after_ms = max(retry_after_ms, identifier_ttl_ms)

        if retry_after_ms > 0:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=max(1, math.ceil(retry_after_ms / 1000)),
            )
        return RateLimitDecision(allowed=True)

    async def clear_identifier(self, identifier: str) -> None:
        """Clear account lockout after the caller proves possession of the password."""
        try:
            await self._redis.delete(self._identifier_key(identifier))
        except RedisError:
            # Token issuance already succeeded. A transient cleanup failure must not
            # turn a valid login into a client-visible error.
            return
