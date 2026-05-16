import pytest

from wayback_mcp.models import Snapshot
from wayback_mcp.tools.search import search_domain


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_domain_live_archived_domain():
    result = await search_domain("archive.org", limit=5)

    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(r, Snapshot) for r in result)
    assert all(r.original_url for r in result)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_domain_live_prefix_match():
    result = await search_domain("archive.org/about", limit=5)

    assert isinstance(result, list)
    assert all(isinstance(r, Snapshot) for r in result)
