import asyncio

import httpx

from wayback_mcp.config import (
    CACHE_MAX_ENTRIES,
    CACHE_TTLS,
    MAX_RETRIES,
    RATE_LIMITS,
    REQUEST_TIMEOUT,
    USER_AGENT,
    ia_credentials,
)
from wayback_mcp.client.cache import ResponseCache
from wayback_mcp.client.rate_limiter import RateLimiter

_rate_limiter = RateLimiter(RATE_LIMITS)
_response_cache = ResponseCache(CACHE_MAX_ENTRIES, CACHE_TTLS)


async def get(
    url: str,
    rate_key: str,
    params: dict | None = None,
) -> httpx.Response:
    cached = await _response_cache.get(url, params)
    if cached is not None:
        return cached

    await _rate_limiter.acquire(rate_key)

    headers = {"User-Agent": USER_AGENT}
    creds = ia_credentials()
    if creds is not None:
        access, secret = creds
        headers["Authorization"] = f"LOW {access}:{secret}"

    async with httpx.AsyncClient(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        last_response: httpx.Response | None = None

        for attempt in range(MAX_RETRIES):
            response = await client.get(url, params=params)
            last_response = response

            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After", "5")
                retry_after = float(retry_after_raw)
                _rate_limiter.set_retry_after(rate_key, retry_after)
                # Ensure callers can always read the effective Retry-After
                response.headers["Retry-After"] = retry_after_raw
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_after)
                    continue
                break

            if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            break

        if last_response is not None and 200 <= last_response.status_code < 300:
            await _response_cache.set(url, params, rate_key, last_response)

        return last_response  # type: ignore[return-value]
