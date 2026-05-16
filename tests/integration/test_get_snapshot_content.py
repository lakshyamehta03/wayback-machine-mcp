import pytest

from wayback_mcp.models import SnapshotContent
from wayback_mcp.tools.content import get_snapshot_content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_snapshot_content_live_html_page():
    # BBC News homepage has reliable Wayback snapshots in text/html
    result = await get_snapshot_content("https://www.bbc.co.uk/news", timestamp="20200101")

    assert isinstance(result, SnapshotContent)
    assert result.content_type == "html"
    assert result.content is not None
    assert result.word_count is not None and result.word_count > 0
    assert result.snapshot_url.startswith("https://web.archive.org/web/")
    assert result.timestamp is not None
