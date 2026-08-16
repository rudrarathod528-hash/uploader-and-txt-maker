from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


@dataclass(slots=True)
class _Counter:
    count: int
    expires_at: float


class AuthenticationRateLimiter:
    """Process-local fixed-window limiter for login attempts.

    The application runs one replica while the Telegram bot is enabled. Counters reset
    when that process restarts and are intentionally not stored in an external service.
    """

    def __init__(
        self,
        *,
        key_secret: str,
        window_seconds: int,
        identifier_limit: int,
        ip_limit: int,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 100_000,
    ) -> None:
        self._key_secret = key_secret.encode("utf-8")
        self._window_seconds = window_seconds
        self._identifier_limit = identifier_limit
        self._ip_limit = ip_limit
        self._clock = clock
        self._max_entries = max_entries
        self._counters: dict[str, _Counter] = {}
        self._lock = asyncio.Lock()

    def _digest(self, scope: str, value: str) -> str:
        return hmac.new(
            self._key_secret,
            f"{scope}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _identifier_key(self, identifier: str) -> str:
        return f"auth-limit:id:{self._digest('identifier', identifier)}"

    def _consume_key(self, key: str, now: float) -> _Counter:
        counter = self._counters.get(key)
        if counter is None or counter.expires_at <= now:
            counter = _Counter(count=1, expires_at=now + self._window_seconds)
            self._counters[key] = counter
        else:
            counter.count += 1
        return counter

    def _prune(self, now: float) -> None:
        expired = [
            key for key, counter in self._counters.items() if counter.expires_at <= now
        ]
        for key in expired:
            self._counters.pop(key, None)

        overflow = len(self._counters) - self._max_entries
        if overflow > 0:
            oldest = sorted(
                self._counters, key=lambda key: self._counters[key].expires_at
            )[:overflow]
            for key in oldest:
                self._counters.pop(key, None)

    async def consume(self, *, client_ip: str, identifier: str) -> RateLimitDecision:
        now = self._clock()
        ip_key = f"auth-limit:ip:{self._digest('ip', client_ip)}"
        identifier_key = self._identifier_key(identifier)

        async with self._lock:
            self._prune(now)
            ip_counter = self._consume_key(ip_key, now)
            identifier_counter = self._consume_key(identifier_key, now)
            self._prune(now)

            retry_after = 0.0
            if ip_counter.count > self._ip_limit:
                retry_after = max(retry_after, ip_counter.expires_at - now)
            if identifier_counter.count > self._identifier_limit:
                retry_after = max(retry_after, identifier_counter.expires_at - now)

        if retry_after > 0:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=max(1, math.ceil(retry_after)),
            )
        return RateLimitDecision(allowed=True)

    async def clear_identifier(self, identifier: str) -> None:
        """Clear account lockout after the caller proves possession of the password."""
        async with self._lock:
            self._counters.pop(self._identifier_key(identifier), None)
