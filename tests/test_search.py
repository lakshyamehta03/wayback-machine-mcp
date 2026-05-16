import pytest
import respx
import httpx

from wayback_mcp.tools.search import search_domain, _match_type
from wayback_mcp.models import Snapshot, ToolError

CDX_URL = "http://web.archive.org/cdx/search/cdx"

CDX_HEADER = ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]

def cdx_row(url, timestamp="20230101120000", mimetype="text/html", statuscode="200"):
    urlkey = url.replace("https://", "").replace("http://", "").replace("/", ",")
    return [urlkey, timestamp, url, mimetype, statuscode, "SHA1:abc", "12345"]


def cdx_response(*rows):
    return [CDX_HEADER] + list(rows)


# ── Cycle 1: matchType selection logic ───────────────────────────────────────

def test_match_type_bare_domain():
    assert _match_type("example.com") == "domain"


def test_match_type_domain_with_path():
    assert _match_type("example.com/blog") == "prefix"


def test_match_type_domain_with_deep_path():
    assert _match_type("example.com/blog/posts/2023") == "prefix"


# ── Cycle 2: bare-domain happy path ──────────────────────────────────────────

CDX_DOMAIN_RESPONSE = [
    ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    ["com,example)/", "20230601120000", "http://example.com/", "text/html", "200", "SHA1:abc", "12345"],
    ["com,example)/about", "20230602130000", "http://example.com/about", "text/html", "200", "SHA1:def", "8765"],
]


@pytest.mark.asyncio
async def test_search_domain_bare_domain_returns_snapshots():
    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        result = await search_domain("example.com")

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(r, Snapshot) for r in result)
    assert result[0].original_url == "http://example.com/"
    assert result[0].status_code == "200"


@pytest.mark.asyncio
async def test_search_domain_always_sends_collapse_urlkey():
    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        await search_domain("example.com")

    request = route.calls.last.request
    assert "collapse=urlkey" in str(request.url)


# ── Cycle 3: prefix-match happy path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_domain_prefix_sends_matchtype_prefix():
    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        await search_domain("example.com/blog")

    request = route.calls.last.request
    assert "matchType=prefix" in str(request.url)


@pytest.mark.asyncio
async def test_search_domain_bare_domain_sends_matchtype_domain():
    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        await search_domain("example.com")

    request = route.calls.last.request
    assert "matchType=domain" in str(request.url)


# ── Cycle 4: status-code filter ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_domain_status_code_filter_forwarded():
    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        await search_domain("example.com", status_code="200")

    request = route.calls.last.request
    assert "filter=statuscode%3A200" in str(request.url) or "statuscode:200" in str(request.url)


# ── Cycle 5: empty range / JSONDecodeError returns [] ────────────────────────

@pytest.mark.asyncio
async def test_search_domain_json_decode_error_returns_empty_list():
    with respx.mock:
        respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, content=b"no results for this date range")
        )
        result = await search_domain("example.com", from_date="20000101", to_date="20000102")

    assert result == []


@pytest.mark.asyncio
async def test_search_domain_header_only_cdx_response_returns_empty_list():
    header_only = [["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]]
    with respx.mock:
        respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=header_only)
        )
        result = await search_domain("example.com")

    assert result == []


# ── Cycle 6: large response truncation ───────────────────────────────────────

@pytest.mark.asyncio
async def test_search_domain_limit_capped_at_config_max():
    from wayback_mcp.config import CDX_MAX_RESULTS

    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        await search_domain("example.com", limit=CDX_MAX_RESULTS + 999)

    request = route.calls.last.request
    assert f"limit={CDX_MAX_RESULTS}" in str(request.url)


@pytest.mark.asyncio
async def test_search_domain_default_limit_sent():
    from wayback_mcp.config import CDX_MAX_RESULTS

    with respx.mock:
        route = respx.get(CDX_URL).mock(
            return_value=httpx.Response(200, json=CDX_DOMAIN_RESPONSE)
        )
        await search_domain("example.com")

    request = route.calls.last.request
    assert f"limit={CDX_MAX_RESULTS}" in str(request.url)
