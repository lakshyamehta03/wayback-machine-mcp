from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from wayback_mcp.client.http import _response_cache, get
from wayback_mcp.config import CDX_URL
from wayback_mcp.models import ToolError
from wayback_mcp.server import mcp
from wayback_mcp.tools.snapshots import lookup_snapshots


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("wayback_mcp.client.http.asyncio.sleep", AsyncMock())


@pytest.fixture(autouse=True)
def _clear_cache():
    _response_cache.clear()
    yield
    _response_cache.clear()


@pytest.mark.asyncio
async def test_authorization_header_sent_when_both_env_vars_set(monkeypatch):
    monkeypatch.setenv("WAYBACK_MCP_IA_ACCESS_KEY", "ACCESS123")
    monkeypatch.setenv("WAYBACK_MCP_IA_SECRET_KEY", "SECRET456")

    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(200, json={}))
        await get(url, "cdx", params={"url": "bbc.com"})

    assert route.call_count == 1
    auth = route.calls[0].request.headers.get("Authorization")
    assert auth == "LOW ACCESS123:SECRET456"


@pytest.mark.parametrize(
    "env",
    [
        {},  # neither set
        {"WAYBACK_MCP_IA_ACCESS_KEY": "ACCESS123"},  # only access
        {"WAYBACK_MCP_IA_SECRET_KEY": "SECRET456"},  # only secret
        {"WAYBACK_MCP_IA_ACCESS_KEY": "", "WAYBACK_MCP_IA_SECRET_KEY": ""},  # both empty
    ],
)
@pytest.mark.asyncio
async def test_no_authorization_header_when_credentials_incomplete(monkeypatch, env):
    monkeypatch.delenv("WAYBACK_MCP_IA_ACCESS_KEY", raising=False)
    monkeypatch.delenv("WAYBACK_MCP_IA_SECRET_KEY", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    url = "https://archive.org/wayback/available"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(200, json={}))
        await get(url, "cdx", params={"url": "bbc.com"})

    assert route.call_count == 1
    assert route.calls[0].request.headers.get("Authorization") is None


@pytest.mark.asyncio
async def test_setup_authentication_prompt_renders_unconfigured_state(monkeypatch):
    monkeypatch.delenv("WAYBACK_MCP_IA_ACCESS_KEY", raising=False)
    monkeypatch.delenv("WAYBACK_MCP_IA_SECRET_KEY", raising=False)

    result = await mcp.get_prompt("setup_authentication", arguments={})

    assert len(result.messages) >= 1
    text = result.messages[0].content.text
    # Points the user at the keys page
    assert "archive.org/account/s3.php" in text
    # Names the env vars the user will set
    assert "WAYBACK_MCP_IA_ACCESS_KEY" in text
    assert "WAYBACK_MCP_IA_SECRET_KEY" in text
    # Includes the claude_desktop_config.json env-block snippet
    assert "claude_desktop_config.json" in text
    assert '"env"' in text or "env block" in text.lower()
    # Tells the user to restart Claude Desktop
    assert "restart" in text.lower()


@pytest.mark.asyncio
async def test_setup_authentication_prompt_renders_configured_state(monkeypatch):
    monkeypatch.setenv("WAYBACK_MCP_IA_ACCESS_KEY", "ACCESS123")
    monkeypatch.setenv("WAYBACK_MCP_IA_SECRET_KEY", "SECRET456")

    result = await mcp.get_prompt("setup_authentication", arguments={})
    text = result.messages[0].content.text

    assert "credentials detected" in text.lower() or "✓" in text
    # Must not nudge the already-authenticated user to set things up again
    assert "archive.org/account/s3.php" not in text
    # Must not leak the actual credentials
    assert "ACCESS123" not in text
    assert "SECRET456" not in text


@pytest.mark.asyncio
async def test_429_error_includes_auth_hint_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WAYBACK_MCP_IA_ACCESS_KEY", raising=False)
    monkeypatch.delenv("WAYBACK_MCP_IA_SECRET_KEY", raising=False)

    with respx.mock:
        respx.get(CDX_URL).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"})
        )
        result = await lookup_snapshots("bbc.com")

    assert isinstance(result, ToolError)
    assert "30" in result.error  # Retry-After preserved
    assert "setup_authentication" in result.error  # names the prompt


@pytest.mark.asyncio
async def test_429_error_omits_auth_hint_when_already_configured(monkeypatch):
    monkeypatch.setenv("WAYBACK_MCP_IA_ACCESS_KEY", "ACCESS123")
    monkeypatch.setenv("WAYBACK_MCP_IA_SECRET_KEY", "SECRET456")

    with respx.mock:
        respx.get(CDX_URL).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"})
        )
        result = await lookup_snapshots("bbc.com")

    assert isinstance(result, ToolError)
    assert "30" in result.error
    # No upsell when the user has already done the work
    assert "setup_authentication" not in result.error
    assert "archive.org/account/s3.php" not in result.error
