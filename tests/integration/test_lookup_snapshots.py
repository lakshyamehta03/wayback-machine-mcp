import pytest

from wayback_mcp.models import Snapshot, ToolError
from wayback_mcp.tools.snapshots import lookup_snapshots


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lookup_snapshots_live_known_url():
    # archive.org has a long CDX history — at least one snapshot guaranteed
    result = await lookup_snapshots("archive.org", limit=5)

    # CDX is regularly flaky (503s, rate-limit). Surface upstream failure as a
    # skip rather than a hard fail — we still verify the happy-path shape when
    # the server cooperates.
    if isinstance(result, ToolError):
        pytest.skip(f"CDX upstream unavailable: {result.error[:120]}")

    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(s, Snapshot) for s in result)
    s = result[0]
    assert s.timestamp
    assert s.original_url
    assert s.status_code
    assert s.wayback_url.startswith("https://web.archive.org/web/")
    assert "if_" in s.content_url
