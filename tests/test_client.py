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


# ── #25: parse_item_metadata prefers "files" over "files_sample" ─────────────

from wayback_mcp.client.parsers import parse_item_metadata


def test_parse_item_metadata_prefers_files_over_files_sample():
    """IA's metadata response normally carries the full file list under
    'files'. Without this preference, items return file_count=0 even when
    the response actually contains files."""
    data = {
        "metadata": {"identifier": "test-item", "title": "Test"},
        "files": [{"name": "a.pdf"}, {"name": "b.pdf"}, {"name": "c.pdf"}],
        "files_sample": [],
    }
    meta = parse_item_metadata(data)
    assert meta.file_count == 3
    assert len(meta.files) == 3


def test_parse_item_metadata_falls_back_to_files_sample():
    """Older or specialised items may have only files_sample. Backward
    compatible — the parser must still find them."""
    data = {
        "metadata": {"identifier": "test-item"},
        "files_sample": [{"name": "x.txt"}, {"name": "y.txt"}],
    }
    meta = parse_item_metadata(data)
    assert meta.file_count == 2


def test_parse_item_metadata_empty_when_neither_field_present():
    data = {"metadata": {"identifier": "test-item"}}
    meta = parse_item_metadata(data)
    assert meta.file_count == 0
    assert meta.files == []
