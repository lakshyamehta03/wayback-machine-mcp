import asyncio

import httpx

from wayback_mcp.config import MAX_RETRIES, RATE_LIMITS, REQUEST_TIMEOUT, USER_AGENT
from wayback_mcp.client.rate_limiter import RateLimiter

_rate_limiter = RateLimiter(RATE_LIMITS)


async def get(
    url: str,
    rate_key: str,
    params: dict | None = None,
) -> httpx.Response:
    await _rate_limiter.acquire(rate_key)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        last_response: httpx.Response | None = None

        for attempt in range(MAX_RETRIES):
            response = await client.get(url, params=params)
            last_response = response

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "5"))
                _rate_limiter.set_retry_after(rate_key, retry_after)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_after)
                    continue
                break

            if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            break

        return last_response  # type: ignore[return-value]
