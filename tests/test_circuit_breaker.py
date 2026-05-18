import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from wayback_mcp.client import http as _http_module
from wayback_mcp.client.circuit_breaker import CircuitBreaker
from wayback_mcp.client.http import _backoff_seconds, get
from wayback_mcp.config import CDX_URL


# ── unit: backoff schedule ────────────────────────────────────────────────────

def test_backoff_is_exponential_capped_at_30():
    assert _backoff_seconds(0) == 1.0
    assert _backoff_seconds(1) == 2.0
    assert _backoff_seconds(2) == 4.0
    assert _backoff_seconds(3) == 8.0
    assert _backoff_seconds(4) == 16.0
    assert _backoff_seconds(5) == 30.0   # 32 capped to 30
    assert _backoff_seconds(10) == 30.0  # high attempts still capped


# ── unit: breaker state machine ──────────────────────────────────────────────

def test_breaker_opens_after_threshold_failures():
    cb = CircuitBreaker(threshold=5, cooldown=30.0)
    assert not cb.is_open("cdx")
    for _ in range(4):
        cb.record_failure("cdx")
    assert not cb.is_open("cdx")   # still under threshold
    cb.record_failure("cdx")        # 5th — trips
    assert cb.is_open("cdx")


def test_breaker_success_resets_failure_count():
    cb = CircuitBreaker(threshold=5, cooldown=30.0)
    for _ in range(4):
        cb.record_failure("cdx")
    cb.record_success("cdx")
    for _ in range(4):
        cb.record_failure("cdx")
    assert not cb.is_open("cdx")    # 4 failures since the reset, not 8 total


def test_breaker_auto_closes_after_cooldown(monkeypatch):
    """is_open() must return False (and reset state) once cooldown elapses."""
    import wayback_mcp.client.circuit_breaker as cb_mod
    fake_now = [1000.0]
    monkeypatch.setattr(cb_mod.time, "monotonic", lambda: fake_now[0])

    cb = CircuitBreaker(threshold=2, cooldown=30.0)
    cb.record_failure("cdx")
    cb.record_failure("cdx")
    assert cb.is_open("cdx")

    fake_now[0] = 1030.5
    assert not cb.is_open("cdx")
    # And it's fully reset — a single new failure should not re-trip.
    cb.record_failure("cdx")
    assert not cb.is_open("cdx")


def test_breaker_is_per_bucket():
    cb = CircuitBreaker(threshold=3, cooldown=30.0)
    for _ in range(3):
        cb.record_failure("cdx")
    assert cb.is_open("cdx")
    assert not cb.is_open("metadata")   # different bucket, untouched


# ── integration: http.get respects the breaker ───────────────────────────────

@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Make backoff sleeps instant so this file isn't slow."""
    monkeypatch.setattr("wayback_mcp.client.http.asyncio.sleep", AsyncMock())


@pytest.mark.asyncio
async def test_http_get_short_circuits_when_breaker_open(monkeypatch):
    # Pre-trip the breaker for the cdx bucket.
    _http_module._circuit_breaker.record_failure("cdx")
    _http_module._circuit_breaker._failures["cdx"] = 99
    _http_module._circuit_breaker._opened_at["cdx"] = 1_000_000.0
    monkeypatch.setattr(
        "wayback_mcp.client.circuit_breaker.time.monotonic",
        lambda: 1_000_000.0,
    )

    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[]))
        result = await get(CDX_URL, "cdx", params={"url": "bbc.com"})

    # No HTTP call should have been issued.
    assert route.call_count == 0
    from wayback_mcp.models import ToolError
    assert isinstance(result, ToolError)
    assert "degraded" in result.error.lower()


@pytest.mark.asyncio
async def test_http_get_records_failure_on_5xx():
    # Stub all 5 attempts as 503; breaker should accumulate failures.
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(503))
        await get(CDX_URL, "cdx", params={"url": "bbc.com"})

    # MAX_RETRIES=5 attempts, all 503 → 5 failures recorded → breaker open.
    assert _http_module._circuit_breaker.is_open("cdx")


@pytest.mark.asyncio
async def test_http_get_does_not_record_429_as_failure():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "1"}))
        await get(CDX_URL, "cdx", params={"url": "bbc.com"})

    # 429 is "rate limited," not "degraded" — must not trip the breaker.
    assert not _http_module._circuit_breaker.is_open("cdx")
    assert _http_module._circuit_breaker._failures.get("cdx", 0) == 0
