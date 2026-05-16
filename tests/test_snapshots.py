import pytest
import respx
import httpx

from wayback_mcp.tools.snapshots import check_availability
from wayback_mcp.models import AvailabilityResult, ToolError

AVAILABILITY_URL = "https://archive.org/wayback/available"

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
async def test_check_availability_malformed_response():
    with respx.mock:
        respx.get(AVAILABILITY_URL).mock(
            return_value=httpx.Response(200, content=b"not json at all <<<")
        )
        result = await check_availability("bbc.com")

    assert isinstance(result, ToolError)
    assert result.error is not None
