import pytest

from wayback_mcp.server import mcp


@pytest.mark.asyncio
async def test_research_topic_renders_with_workflow_steps():
    result = await mcp.get_prompt(
        "research_topic",
        arguments={"topic": "climate change", "year_from": 2000, "year_to": 2010},
    )

    assert len(result.messages) >= 1
    text = result.messages[0].content.text

    assert "climate change" in text
    assert "2000" in text
    assert "2010" in text
    assert "search_archive" in text
    assert "get_item_metadata" in text


@pytest.mark.asyncio
async def test_track_site_changes_renders_with_sampling_workflow():
    result = await mcp.get_prompt(
        "track_site_changes",
        arguments={
            "url": "https://example.com",
            "from_date": "20100101",
            "to_date": "20200101",
            "sample_size": 5,
        },
    )

    text = result.messages[0].content.text

    assert "https://example.com" in text
    assert "20100101" in text
    assert "20200101" in text
    assert "lookup_snapshots" in text
    assert "get_snapshot_content" in text
    # Instructions must direct sampling, not exhaustive fetching
    assert "sample" in text.lower()
    assert "first" in text.lower() and "last" in text.lower()


@pytest.mark.asyncio
async def test_audit_link_rot_uses_check_availability_iteration_not_bulk():
    result = await mcp.get_prompt(
        "audit_link_rot",
        arguments={"urls": "https://example.com/a\nhttps://example.com/b"},
    )

    text = result.messages[0].content.text

    assert "https://example.com/a" in text
    assert "https://example.com/b" in text
    assert "check_availability" in text
    # The dropped bulk endpoint must not be referenced
    assert "bulk_check_links" not in text
    # Should describe per-URL iteration
    assert "each" in text.lower() or "iterate" in text.lower()
