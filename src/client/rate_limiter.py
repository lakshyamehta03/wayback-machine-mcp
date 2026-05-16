import asyncio
import time


class TokenBucket:
    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self._rate = rate
        self._capacity = capacity or rate * 10
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


class RateLimiter:
    def __init__(self, rates: dict[str, float]) -> None:
        self._buckets: dict[str, TokenBucket] = {
            key: TokenBucket(rate) for key, rate in rates.items()
        }
        self._retry_after: dict[str, float] = {}

    async def acquire(self, key: str) -> None:
        if key in self._retry_after:
            wait_until = self._retry_after.pop(key)
            remaining = wait_until - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)

        if key in self._buckets:
            await self._buckets[key].acquire()

    def set_retry_after(self, key: str, seconds: float) -> None:
        self._retry_after[key] = time.monotonic() + seconds
