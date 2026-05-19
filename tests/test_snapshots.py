import pytest
import respx
import httpx

from wayback_mcp.tools.snapshots import check_availability, lookup_snapshots
from wayback_mcp.models import AvailabilityResult, Snapshot, ToolError

CDX_URL = "http://web.archive.org/cdx/search/cdx"

CDX_MULTI_ROW = [
    ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    ["20050102091250", "http://www.bbc.com/", "text/html", "200", "SHA1:ABC123", "1234"],
    ["20060305120000", "http://www.bbc.com/news", "text/html", "301", "SHA1:DEF456", "500"],
]

CDX_SINGLE_ROW = [
    ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    ["20050102091250", "http://www.bbc.com/", "text/html", "200", "SHA1:ABC123", "1234"],
]

CDX_EMPTY = [["timestamp", "original", "mimetype", "statuscode", "digest", "length"]]


@pytest.mark.asyncio
async def test_check_availability_archived_url():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_SINGLE_ROW))
        result = await check_availability("bbc.com")

    assert isinstance(result, AvailabilityResult)
    assert result.available is True
    assert result.snapshot_url == "https://web.archive.org/web/20050102091250/http://www.bbc.com/"
    assert result.timestamp == "20050102091250"
    assert result.status == "200"
    assert result.original_url == "bbc.com"
    assert result.error is None


@pytest.mark.asyncio
async def test_check_availability_unarchived_url():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_EMPTY))
        result = await check_availability("xyzzy-never-archived-abc123.com")

    assert isinstance(result, AvailabilityResult)
    assert result.available is False
    assert result.snapshot_url is None
    assert result.timestamp is None
    assert result.status is None
    assert result.error is None


@pytest.mark.asyncio
async def test_check_availability_forwards_timestamp():
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_SINGLE_ROW))
        await check_availability("bbc.com", timestamp="20050101")

    assert route.called
    qs = str(route.calls.last.request.url)
    # closest_to flows through as CDX's closest=/sort=closest pair
    assert "closest=20050101" in qs
    assert "sort=closest" in qs


@pytest.mark.asyncio
async def test_check_availability_no_timestamp_uses_fast_latest():
    """Without a timestamp, check_availability should ride CDX's fastLatest
    path (cheap, single most-recent capture) rather than re-querying the
    closest-in-time index."""
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_SINGLE_ROW))
        await check_availability("bbc.com")

    qs = str(route.calls.last.request.url)
    assert "fastLatest=true" in qs


@pytest.mark.asyncio
async def test_check_availability_429_retry_after():
    with respx.mock:
        respx.get(CDX_URL).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}, json={}),
                httpx.Response(200, json=CDX_SINGLE_ROW),
            ]
        )
        result = await check_availability("bbc.com")

    assert isinstance(result, AvailabilityResult)
    assert result.available is True


@pytest.mark.asyncio
async def test_lookup_snapshots_returns_snapshots():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        result = await lookup_snapshots("bbc.com")

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(s, Snapshot) for s in result)
    s = result[0]
    assert s.timestamp == "20050102091250"
    assert s.original_url == "http://www.bbc.com/"
    assert s.status_code == "200"
    assert s.mimetype == "text/html"
    assert s.wayback_url == "https://web.archive.org/web/20050102091250/http://www.bbc.com/"
    assert s.content_url == "https://web.archive.org/web/20050102091250if_/http://www.bbc.com/"


@pytest.mark.asyncio
async def test_lookup_snapshots_header_only_returns_empty_list():
    header_only = [["timestamp", "original", "mimetype", "statuscode", "digest", "length"]]
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=header_only))
        result = await lookup_snapshots("never-archived-xyzzy99.com")

    assert result == []


@pytest.mark.asyncio
async def test_lookup_snapshots_non_json_response_returns_tool_error():
    with respx.mock:
        respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, content=b"no results for this date range")
        )
        result = await lookup_snapshots("bbc.com", from_date="20300101", to_date="20300102")

    assert isinstance(result, ToolError)
    assert "malformed response" in result.error
    assert "no results for this date range" in result.error


@pytest.mark.asyncio
async def test_lookup_snapshots_status_code_filter():
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        await lookup_snapshots("bbc.com", status_code="200")

    assert route.called
    assert "filter=statuscode%3A200" in str(route.calls.last.request.url)


@pytest.mark.asyncio
async def test_check_availability_malformed_response():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, content=b"not json at all <<<"))
        result = await check_availability("bbc.com")

    assert isinstance(result, ToolError)
    assert result.error is not None


# ── #27: collapse default + latest/fastLatest ────────────────────────────────

@pytest.mark.asyncio
async def test_lookup_snapshots_sends_default_collapse_timestamp_8():
    """Without `collapse` argument, the default per-day collapse is sent so
    popular URLs don't return one row per crawler hit."""
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        await lookup_snapshots("bbc.com")

    qs = str(route.calls.last.request.url)
    assert "collapse=timestamp%3A8" in qs or "collapse=timestamp:8" in qs


@pytest.mark.asyncio
async def test_lookup_snapshots_explicit_collapse_overrides_default():
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        await lookup_snapshots("bbc.com", collapse="digest")

    qs = str(route.calls.last.request.url)
    assert "collapse=digest" in qs
    assert "timestamp" not in qs.split("collapse=")[1].split("&")[0]


@pytest.mark.asyncio
async def test_lookup_snapshots_empty_collapse_disables_collapsing():
    """`collapse=""` is the explicit opt-out — sends no collapse param at all."""
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        await lookup_snapshots("bbc.com", collapse="")

    qs = str(route.calls.last.request.url)
    assert "collapse=" not in qs


@pytest.mark.asyncio
async def test_lookup_snapshots_latest_sends_fastlatest_and_negative_limit():
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        await lookup_snapshots("bbc.com", latest=True, limit=3)

    qs = str(route.calls.last.request.url)
    assert "fastLatest=true" in qs
    assert "limit=-3" in qs


@pytest.mark.asyncio
async def test_lookup_snapshots_latest_with_date_filter_returns_error():
    result = await lookup_snapshots("bbc.com", latest=True, from_date="20200101")
    assert isinstance(result, ToolError)
    assert "latest" in result.error.lower()


@pytest.mark.asyncio
async def test_lookup_snapshots_latest_defaults_to_5_when_no_limit():
    with respx.mock:
        route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_MULTI_ROW))
        await lookup_snapshots("bbc.com", latest=True)

    qs = str(route.calls.last.request.url)
    assert "limit=-5" in qs
    assert "fastLatest=true" in qs
