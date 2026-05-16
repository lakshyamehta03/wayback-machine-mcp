import pytest
from unittest.mock import AsyncMock, patch

from wayback_mcp.client.rate_limiter import RateLimiter, TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_no_sleep_when_full():
    bucket = TokenBucket(rate=10.0)  # starts with 100 tokens

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await bucket.acquire()

    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_token_bucket_sleeps_when_empty():
    bucket = TokenBucket(rate=1.0, capacity=1.0)
    await bucket.acquire()  # consumes the single token

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await bucket.acquire()

    mock_sleep.assert_called_once()
    sleep_duration = mock_sleep.call_args[0][0]
    # Whatever fraction of a second is needed to accumulate 1 token at rate=1.0
    assert 0 < sleep_duration <= 1.0


@pytest.mark.asyncio
async def test_rate_limiter_no_delay_on_first_call():
    limiter = RateLimiter({"cdx": 10.0})

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.acquire("cdx")

    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limiter_honours_retry_after():
    limiter = RateLimiter({"cdx": 100.0})  # generous bucket, won't add delay
    limiter.set_retry_after("cdx", 5.0)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.acquire("cdx")

    mock_sleep.assert_called_once()
    sleep_duration = mock_sleep.call_args[0][0]
    assert sleep_duration > 4.0  # close to 5.0 minus negligible elapsed time


@pytest.mark.asyncio
async def test_rate_limiter_clears_retry_after_after_use():
    limiter = RateLimiter({"cdx": 100.0})
    limiter.set_retry_after("cdx", 1.0)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await limiter.acquire("cdx")

    # retry_after cleared — second acquire must not sleep
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.acquire("cdx")

    mock_sleep.assert_not_called()
