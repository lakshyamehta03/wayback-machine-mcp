from unittest.mock import AsyncMock

import pytest
import respx
import httpx

from wayback_mcp.client.cache import ResponseCache
from wayback_mcp.client.http import get, _response_cache
from wayback_mcp.config import CACHE_TTLS


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("wayback_mcp.client.http.asyncio.sleep", AsyncMock())


@pytest.mark.asyncio
async def test_second_get_returns_cached_response_without_network():
    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        r1 = await get(url, "cdx", params={"url": "bbc.com"})
        r2 = await get(url, "cdx", params={"url": "bbc.com"})

    assert route.call_count == 1
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}


@pytest.mark.asyncio
async def test_429_response_is_not_cached():
    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0"}, json={})
        )

        r1 = await get(url, "cdx", params={"url": "bbc.com"})
        r2 = await get(url, "cdx", params={"url": "bbc.com"})

    assert r1.status_code == 429
    assert r2.status_code == 429
    # Each call retries MAX_RETRIES times; cache must not short-circuit the second call
    assert route.call_count >= 2


@pytest.mark.asyncio
async def test_cache_entry_expires_after_ttl(monkeypatch):
    fake_time = [1000.0]
    monkeypatch.setattr(_response_cache, "_now", lambda: fake_time[0])

    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(200, json={"v": 1}))

        await get(url, "cdx", params={"url": "bbc.com"})
        # Advance just past the cdx TTL
        fake_time[0] += CACHE_TTLS["cdx"] + 1
        await get(url, "cdx", params={"url": "bbc.com"})

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_different_params_are_distinct_cache_entries():
    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(200, json={"ok": True}))

        await get(url, "cdx", params={"url": "bbc.com"})
        await get(url, "cdx", params={"url": "nytimes.com"})
        await get(url, "cdx", params={"url": "bbc.com"})  # cached
        await get(url, "cdx", params={"url": "nytimes.com"})  # cached

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_check_availability_429_error_includes_retry_after():
    from wayback_mcp.tools.snapshots import check_availability
    from wayback_mcp.models import ToolError

    url = "https://archive.org/wayback/available"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "12"}, json={})
        )
        result = await check_availability("bbc.com")

    assert isinstance(result, ToolError)
    assert result.error is not None
    assert "12" in result.error


@pytest.mark.asyncio
async def test_lookup_snapshots_429_error_includes_retry_after():
    from wayback_mcp.tools.snapshots import lookup_snapshots
    from wayback_mcp.models import ToolError

    url = "http://web.archive.org/cdx/search/cdx"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "7"}, json={})
        )
        result = await lookup_snapshots("bbc.com")

    assert isinstance(result, ToolError)
    assert "7" in result.error


@pytest.mark.asyncio
async def test_get_item_metadata_429_error_includes_retry_after():
    from wayback_mcp.tools.content import get_item_metadata
    from wayback_mcp.models import ToolError

    url = "https://archive.org/metadata/some-item"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "20"}, json={})
        )
        result = await get_item_metadata("some-item")

    assert isinstance(result, ToolError)
    assert "20" in result.error


@pytest.mark.asyncio
async def test_search_archive_429_error_includes_retry_after():
    from wayback_mcp.tools.search import search_archive
    from wayback_mcp.models import ToolError

    url = "https://archive.org/advancedsearch.php"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "9"}, json={})
        )
        result = await search_archive("apollo")

    assert isinstance(result, ToolError)
    assert "9" in result.error


@pytest.mark.asyncio
async def test_search_domain_429_error_includes_retry_after():
    from wayback_mcp.tools.search import search_domain
    from wayback_mcp.models import ToolError

    url = "http://web.archive.org/cdx/search/cdx"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "4"}, json={})
        )
        result = await search_domain("bbc.com")

    assert isinstance(result, ToolError)
    assert "4" in result.error


@pytest.mark.asyncio
async def test_get_snapshot_content_429_error_includes_retry_after():
    from wayback_mcp.tools.content import get_snapshot_content
    from wayback_mcp.models import ToolError

    url = "https://archive.org/wayback/available"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "15"}, json={})
        )
        result = await get_snapshot_content("bbc.com")

    assert isinstance(result, ToolError)
    assert "15" in result.error


@pytest.mark.asyncio
async def test_429_with_no_retry_after_header_falls_back_to_default():
    from wayback_mcp.tools.snapshots import check_availability
    from wayback_mcp.models import ToolError

    url = "https://archive.org/wayback/available"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(429, json={}))
        result = await check_availability("bbc.com")

    assert isinstance(result, ToolError)
    # Default fallback from http.py is "5"
    assert "5" in result.error


@pytest.mark.asyncio
async def test_lru_eviction_at_capacity():
    cache = ResponseCache(max_size=2, ttls={"cdx": 3600})
    r = httpx.Response(200, json={"x": 1})

    await cache.set("https://a", None, "cdx", r)
    await cache.set("https://b", None, "cdx", r)
    await cache.set("https://c", None, "cdx", r)  # evicts "a"

    assert await cache.get("https://a", None) is None
    assert await cache.get("https://b", None) is not None
    assert await cache.get("https://c", None) is not None


@pytest.mark.asyncio
async def test_5xx_response_is_not_cached():
    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(503))

        await get(url, "cdx", params={"url": "bbc.com"})
        await get(url, "cdx", params={"url": "bbc.com"})

    assert route.call_count >= 2
