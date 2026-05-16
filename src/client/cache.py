import asyncio
import time
from collections import OrderedDict
from typing import Callable

import httpx

CacheKey = tuple[str, frozenset]


def _make_key(url: str, params: dict | None) -> CacheKey:
    return (url, frozenset(params.items()) if params else frozenset())


class ResponseCache:
    def __init__(
        self,
        max_size: int,
        ttls: dict[str, float],
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_size = max_size
        self._ttls = ttls
        self._now = now
        self._entries: "OrderedDict[CacheKey, tuple[float, int, dict, bytes]]" = OrderedDict()
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        self._entries.clear()

    async def get(self, url: str, params: dict | None) -> httpx.Response | None:
        key = _make_key(url, params)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, status, headers, body = entry
            if self._now() >= expires_at:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
        return httpx.Response(status, headers=headers, content=body)

    async def set(
        self, url: str, params: dict | None, bucket: str, response: httpx.Response
    ) -> None:
        ttl = self._ttls.get(bucket)
        if ttl is None:
            return
        key = _make_key(url, params)
        expires_at = self._now() + ttl
        headers = dict(response.headers)
        body = response.content
        async with self._lock:
            self._entries[key] = (expires_at, response.status_code, headers, body)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_size:
                self._entries.popitem(last=False)
