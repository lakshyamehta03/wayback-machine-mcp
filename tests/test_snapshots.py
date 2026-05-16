import pytest
import respx
import httpx

from wayback_mcp.tools.snapshots import check_availability, lookup_snapshots
from wayback_mcp.models import AvailabilityResult, Snapshot, ToolError

AVAILABILITY_URL = "https://archive.org/wayback/available"
CDX_URL = "http://web.archive.org/cdx/search/cdx"

CDX_MULTI_ROW = [
    ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    ["20050102091250", "http://www.bbc.com/", "text/html", "200", "SHA1:ABC123", "1234"],
    ["20060305120000", "http://www.bbc.com/news", "text/html", "301", "SHA1:DEF456", "500"],
]

ARCHIVED_RESPONSE = {
    "url": "bbc.com",
    "archived_snapshots": {
        "closest": {
            "status": "200",
            "available": True,
            "url": "http://web.archive.org/web/20050102091250/http://www.bbc.com:80/",
            "timestamp": "20050102091250",
        }
    },
}

UNARCHIVED_RESPONSE = {
    "url": "xyzzy-never-archived-abc123.com",
    "archived_snapshots": {},
}


@pytest.mark.asyncio
async def test_check_availability_archived_url():
    with respx.mock:
        respx.get(AVAILABILITY_URL).mock(
            return_value=httpx.Response(200, json=ARCHIVED_RESPONSE)
        )
        result = await check_availability("bbc.com")

    assert isinstance(result, AvailabilityResult)
    assert result.available is True
    assert result.snapshot_url == "http://web.archive.org/web/20050102091250/http://www.bbc.com:80/"
    assert result.timestamp == "20050102091250"
    assert result.status == "200"
    assert result.original_url == "bbc.com"
    assert result.error is None


@pytest.mark.asyncio
async def test_check_availability_unarchived_url():
    with respx.mock:
        respx.get(AVAILABILITY_URL).mock(
            return_value=httpx.Response(200, json=UNARCHIVED_RESPONSE)
        )
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
        route = respx.get(AVAILABILITY_URL).mock(
            return_value=httpx.Response(200, json=ARCHIVED_RESPONSE)
        )
        await check_availability("bbc.com", timestamp="20050101")

    assert route.called
    request = route.calls.last.request
    assert "timestamp=20050101" in str(request.url)


@pytest.mark.asyncio
async def test_check_availability_429_retry_after():
    with respx.mock:
        respx.get(AVAILABILITY_URL).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}, json={}),
                httpx.Response(200, json=ARCHIVED_RESPONSE),
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
async def test_lookup_snapshots_empty_range_returns_empty_list():
    with respx.mock:
        respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, content=b"no results for this date range")
        )
        result = await lookup_snapshots("bbc.com", from_date="20300101", to_date="20300102")

    assert result == []


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
        respx.get(AVAILABILITY_URL).mock(
            return_value=httpx.Response(200, content=b"not json at all <<<")
        )
        result = await check_availability("bbc.com")

    assert isinstance(result, ToolError)
    assert result.error is not None
