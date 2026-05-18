"""HTTP client for outbound IA API calls.

`get()` is the single entry point. Each call flows through, in order:

    cache → circuit breaker → rate limiter → auth → retry loop

The retry loop classifies each attempt as one of: network error, 429, 5xx,
or success — and decides whether to back off, propagate, or return. Failures
in the 5xx / network buckets feed the circuit breaker; 2xx successes reset it.
429 is treated as upstream throttling (not degradation) and never trips the
breaker; it gets its own server-supplied Retry-After back-off.
"""

import asyncio
import time

import httpx

from wayback_mcp.config import (
    CACHE_MAX_ENTRIES,
    CACHE_TTLS,
    CDX_URL,
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    RATE_LIMITS,
    REQUEST_TIMEOUT,
    REQUEST_TIMEOUTS,
    USER_AGENT,
    ia_credentials,
)
from wayback_mcp.client.cache import ResponseCache
from wayback_mcp.client.circuit_breaker import CircuitBreaker
from wayback_mcp.client.rate_limiter import RateLimiter
from wayback_mcp.log import log
from wayback_mcp.models import ToolError, rate_limited_error

_rate_limiter = RateLimiter(RATE_LIMITS)
_response_cache = ResponseCache(CACHE_MAX_ENTRIES, CACHE_TTLS)
_request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
_circuit_breaker = CircuitBreaker()


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff capped at 30s — 1s, 2s, 4s, 8s, 16s, 30s..."""
    return min(30.0, 2.0 ** attempt)


def _build_auth(url: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (headers, cookies) carrying IA credentials, routed by endpoint.

    CDX accepts the IA API key as a cookie (cdx-auth-token=ACCESS-SECRET) and
    routes authenticated traffic into a queue instead of fast-failing with 503
    — verified ~4.6x success-rate improvement under load (#26). Other IA
    endpoints (availability, metadata, search) are S3-style and expect the
    LOW Authorization header. We never send both on the same request —
    behaviour would be undefined.

    When credentials aren't configured, returns empty dicts (anonymous).
    """
    headers: dict[str, str] = {"User-Agent": USER_AGENT}
    cookies: dict[str, str] = {}

    creds = ia_credentials()
    if creds is None:
        return headers, cookies

    access, secret = creds
    if url.startswith(CDX_URL):
        cookies["cdx-auth-token"] = f"{access}-{secret}"
    else:
        headers["Authorization"] = f"LOW {access}:{secret}"
    return headers, cookies


async def get(
    url: str,
    rate_key: str,
    params: dict | None = None,
) -> httpx.Response | ToolError:
    log("get.enter", key=rate_key, url=url)

    # ── stage 1: cache lookup ────────────────────────────────────────────
    cached = await _response_cache.get(url, params)
    if cached is not None:
        log("get.cache_hit", key=rate_key, url=url)
        return cached

    # ── stage 2: circuit-breaker gate (skip the request if the bucket is degraded)
    if _circuit_breaker.is_open(rate_key):
        log("circuit_breaker.open", key=rate_key)
        return ToolError(
            error=(
                f"The Wayback Machine's '{rate_key}' endpoint is currently "
                "degraded (repeated 5xx/network failures). Try again in ~30s."
            )
        )

    # ── stage 3: rate-limit token (per-bucket throttle) ──────────────────
    log("rate_limiter.acquire.start", key=rate_key)
    t0 = time.monotonic()
    await _rate_limiter.acquire(rate_key)
    log("rate_limiter.acquire.end", key=rate_key, waited_s=f"{time.monotonic() - t0:.3f}")

    # ── stage 4: build auth + timeout for this endpoint ──────────────────
    headers, cookies = _build_auth(url)
    timeout = REQUEST_TIMEOUTS.get(rate_key, REQUEST_TIMEOUT)

    # ── stage 5: retry loop — fire request, classify outcome, decide ─────
    async with httpx.AsyncClient(
        headers=headers,
        cookies=cookies,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        last_response: httpx.Response | None = None

        for attempt in range(MAX_RETRIES):
            request_error: httpx.RequestError | None = None
            log("semaphore.acquire.start", key=rate_key, attempt=attempt)
            sem_t0 = time.monotonic()
            async with _request_semaphore:
                log(
                    "semaphore.acquired",
                    key=rate_key,
                    attempt=attempt,
                    waited_s=f"{time.monotonic() - sem_t0:.3f}",
                )
                http_t0 = time.monotonic()
                try:
                    log("http.get.start", key=rate_key, attempt=attempt, timeout=timeout)
                    response = await client.get(url, params=params)
                    log(
                        "http.get.end",
                        key=rate_key,
                        attempt=attempt,
                        status=response.status_code,
                        elapsed_s=f"{time.monotonic() - http_t0:.3f}",
                    )
                except httpx.RequestError as exc:
                    log(
                        "http.get.error",
                        key=rate_key,
                        attempt=attempt,
                        exc=type(exc).__name__,
                        elapsed_s=f"{time.monotonic() - http_t0:.3f}",
                    )
                    request_error = exc
            log("semaphore.released", key=rate_key, attempt=attempt)

            # ─ outcome: network error → backoff & retry, or give up ─
            if request_error is not None:
                _circuit_breaker.record_failure(rate_key)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(_backoff_seconds(attempt))
                    continue
                if isinstance(request_error, httpx.TimeoutException):
                    return ToolError(error=f"Request to the Wayback Machine timed out after {timeout}s.")
                return ToolError(
                    error=f"Request to the Wayback Machine failed: {type(request_error).__name__}."
                )

            last_response = response

            # ─ outcome: 429 → honor server Retry-After ─
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

            # ─ outcome: 5xx → backoff & retry ─
            if response.status_code >= 500:
                _circuit_breaker.record_failure(rate_key)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(_backoff_seconds(attempt))
                    continue
                break

            # ─ outcome: 2xx / 3xx / non-429 4xx → success; reset breaker ─
            # The endpoint is responding, just not always with what we asked for.
            _circuit_breaker.record_success(rate_key)
            break

        # ── stage 6: post-loop — cache 2xx, unwrap exhausted 429, return ─
        if last_response is not None and 200 <= last_response.status_code < 300:
            await _response_cache.set(url, params, rate_key, last_response)

        if last_response is not None and last_response.status_code == 429:
            return rate_limited_error(last_response.headers.get("Retry-After", "5"))

        return last_response  # type: ignore[return-value]
