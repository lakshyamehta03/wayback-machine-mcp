import pytest

from wayback_mcp.models import AvailabilityResult
from wayback_mcp.tools.snapshots import check_availability


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_availability_live_archived():
    # archive.org is always archived
    result = await check_availability("archive.org")

    assert isinstance(result, AvailabilityResult)
    assert result.available is True
    assert result.snapshot_url is not None
    assert result.timestamp is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_availability_live_unarchived():
    result = await check_availability("xyzzy-never-archived-abc123-zz99.com")

    assert isinstance(result, AvailabilityResult)
    assert result.available is False
    assert result.snapshot_url is None
