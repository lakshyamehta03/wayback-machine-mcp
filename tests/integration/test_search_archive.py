import pytest

from wayback_mcp.models import SearchResult
from wayback_mcp.tools.search import search_archive


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_archive_live_topic_query():
    result = await search_archive("climate change", mediatype="texts", limit=5)

    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(r, SearchResult) for r in result)
    assert all(r.identifier for r in result)
    assert all(r.mediatype == "texts" for r in result)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_archive_live_year_range():
    result = await search_archive("financial crisis", year_from=2008, year_to=2010, limit=3)

    assert isinstance(result, list)
    assert all(isinstance(r, SearchResult) for r in result)
