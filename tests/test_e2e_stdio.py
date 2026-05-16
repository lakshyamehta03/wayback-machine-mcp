"""End-to-end stdio smoke test.

Spawns the wayback-mcp server as a real subprocess via the MCP stdio
transport and verifies the protocol surface is wired up correctly. Closes
the gap where in-process tests against `mcp.get_prompt()` pass even if the
stdio entry point is broken, a decorator is missing, or the package is not
installed.

No HTTP-hitting tools are round-tripped here — those are covered by unit
tests with respx mocking. This file only proves the wire protocol works.
"""

from __future__ import annotations

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


SERVER_PARAMS = StdioServerParameters(command="uv", args=["run", "wayback-mcp"])

EXPECTED_TOOLS = {
    "check_availability",
    "lookup_snapshots",
    "search_archive",
    "search_domain",
    "get_snapshot_content",
    "get_item_metadata",
}

EXPECTED_PROMPTS = {
    "research_topic",
    "track_site_changes",
    "audit_link_rot",
    "setup_authentication",
}


@pytest.mark.asyncio
async def test_server_exposes_all_six_tools() -> None:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            names = {t.name for t in result.tools}

    assert names == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_server_exposes_all_three_prompts() -> None:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_prompts()
            names = {p.name for p in result.prompts}

    assert names == EXPECTED_PROMPTS


@pytest.mark.asyncio
async def test_server_exposes_item_resource_template() -> None:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_resource_templates()
            templates = {t.uriTemplate for t in result.resourceTemplates}

    assert "wayback://item/{identifier}" in templates


@pytest.mark.asyncio
async def test_audit_link_rot_prompt_renders_over_stdio() -> None:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.get_prompt(
                "audit_link_rot",
                arguments={"urls": "https://example.com/a\nhttps://example.com/b"},
            )

    assert len(result.messages) >= 1
    text = result.messages[0].content.text
    assert "https://example.com/a" in text
    assert "https://example.com/b" in text
    assert "check_availability" in text
