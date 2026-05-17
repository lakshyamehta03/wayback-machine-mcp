import pytest

from wayback_mcp.server import mcp


@pytest.mark.asyncio
async def test_research_topic_renders_with_workflow_steps():
    result = await mcp.get_prompt(
        "research_topic",
        arguments={"topic": "climate change"},
    )

    assert len(result.messages) >= 1
    text = result.messages[0].content.text

    assert "climate change" in text
    assert "search_archive" in text
    assert "get_item_metadata" in text
    # The model is now responsible for picking year_from/year_to out of the topic
    assert "year_from" in text and "year_to" in text


@pytest.mark.asyncio
async def test_research_topic_accepts_free_text_with_spaces():
    """Regression: slash-command clients (Claude Code/Desktop) pass the user's
    entire free-text input as the topic argument. The signature must not
    declare additional positional kwargs that the client could try to fill by
    splitting on whitespace — that triggered Pydantic int_parsing errors on
    inputs like 'how and which Indian politicians ...'.
    """
    free_text = "how and which Indian politicians appear in the Epstein files"

    result = await mcp.get_prompt(
        "research_topic",
        arguments={"topic": free_text},
    )

    assert free_text in result.messages[0].content.text


@pytest.mark.asyncio
async def test_track_site_changes_renders_with_sampling_workflow():
    result = await mcp.get_prompt(
        "track_site_changes",
        arguments={"url": "https://example.com"},
    )

    text = result.messages[0].content.text

    assert "https://example.com" in text
    assert "lookup_snapshots" in text
    assert "get_snapshot_content" in text
    # Instructions must direct sampling, not exhaustive fetching
    assert "sample" in text.lower()
    assert "first" in text.lower() and "last" in text.lower()
    # Model is now responsible for picking from_date/to_date out of context
    assert "from_date" in text and "to_date" in text


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
