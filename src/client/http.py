import asyncio

import httpx

from wayback_mcp.config import (
    CACHE_MAX_ENTRIES,
    CACHE_TTLS,
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    RATE_LIMITS,
    REQUEST_TIMEOUT,
    REQUEST_TIMEOUTS,
    USER_AGENT,
    ia_credentials,
)
from wayback_mcp.client.cache import ResponseCache
from wayback_mcp.client.rate_limiter import RateLimiter
from wayback_mcp.models import ToolError, rate_limited_error

_rate_limiter = RateLimiter(RATE_LIMITS)
_response_cache = ResponseCache(CACHE_MAX_ENTRIES, CACHE_TTLS)
_request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


async def get(
    url: str,
    rate_key: str,
    params: dict | None = None,
) -> httpx.Response | ToolError:
    cached = await _response_cache.get(url, params)
    if cached is not None:
        return cached

    await _rate_limiter.acquire(rate_key)

    headers = {"User-Agent": USER_AGENT}
    creds = ia_credentials()
    if creds is not None:
        access, secret = creds
        headers["Authorization"] = f"LOW {access}:{secret}"

    timeout = REQUEST_TIMEOUTS.get(rate_key, REQUEST_TIMEOUT)

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        last_response: httpx.Response | None = None

        for attempt in range(MAX_RETRIES):
            request_error: httpx.RequestError | None = None
            async with _request_semaphore:
                try:
                    response = await client.get(url, params=params)
                except httpx.RequestError as exc:
                    request_error = exc

            if request_error is not None:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                if isinstance(request_error, httpx.TimeoutException):
                    return ToolError(error=f"Request to the Wayback Machine timed out after {timeout}s.")
                return ToolError(
                    error=f"Request to the Wayback Machine failed: {type(request_error).__name__}."
                )

            last_response = response

            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After", "5")
                retry_after = float(retry_after_raw)
                # Ensure callers can always read the effective Retry-After
                response.headers["Retry-After"] = retry_after_raw
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_after)
                    continue
                # Retries exhausted — record cooldown for the next top-level call
                _rate_limiter.set_retry_after(rate_key, retry_after)
                break

            if response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            break

        if last_response is not None and 200 <= last_response.status_code < 300:
            await _response_cache.set(url, params, rate_key, last_response)

        if last_response is not None and last_response.status_code == 429:
            return rate_limited_error(last_response.headers.get("Retry-After", "5"))

        return last_response  # type: ignore[return-value]
