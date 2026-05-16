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


# ── search_archive: Cycle 1 — bare query passthrough ─────────────────────────

def test_build_query_bare_query():
    from wayback_mcp.tools.search import _build_query
    assert _build_query("financial crisis") == "financial crisis"


# ── Cycle 2: mediatype folded into q= ────────────────────────────────────────

def test_build_query_with_mediatype():
    from wayback_mcp.tools.search import _build_query
    assert _build_query("financial crisis", mediatype="texts") == "financial crisis AND mediatype:texts"


# ── Cycle 3: year range folded into q= ───────────────────────────────────────

def test_build_query_with_year_range():
    from wayback_mcp.tools.search import _build_query
    assert _build_query("climate change", year_from=2008, year_to=2010) == "climate change AND year:[2008 TO 2010]"


# ── Cycle 4: partial year range ──────────────────────────────────────────────

def test_build_query_year_from_only():
    from wayback_mcp.tools.search import _build_query
    assert _build_query("climate change", year_from=2008) == "climate change AND year:[2008 TO *]"


def test_build_query_year_to_only():
    from wayback_mcp.tools.search import _build_query
    assert _build_query("climate change", year_to=2010) == "climate change AND year:[* TO 2010]"


# ── Cycle 5: search_archive happy path ───────────────────────────────────────

SEARCH_URL = "https://archive.org/advancedsearch.php"

SEARCH_HAPPY_RESPONSE = {
    "response": {
        "numFound": 2,
        "start": 0,
        "docs": [
            {
                "identifier": "elnouparadigmade0000soro",
                "title": "El Nou paradigma dels mercats financers",
                "mediatype": "texts",
                "year": 2008,
                "creator": "Soros, George",
                "subject": ["Crisis economiques", "Mercats financers"],
                "downloads": 23,
            },
            {
                "identifier": "defaultlinewhygl0000isla_q6s7",
                "title": "The default line",
                "mediatype": "texts",
                "year": 2013,
                "creator": "Islam, Faisal, author",
                "subject": ["Global Financial Crisis, 2008-2009"],
                "downloads": 19,
            },
        ],
    }
}


@pytest.mark.asyncio
async def test_search_archive_happy_path_returns_search_results():
    from wayback_mcp.tools.search import search_archive
    from wayback_mcp.models import SearchResult

    with respx.mock:
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=SEARCH_HAPPY_RESPONSE)
        )
        result = await search_archive("financial crisis")

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(r, SearchResult) for r in result)
    assert result[0].identifier == "elnouparadigmade0000soro"
    assert result[0].title == "El Nou paradigma dels mercats financers"
    assert result[0].year == 2008
    assert result[0].downloads == 23


# ── Cycle 6: sparse result — optional fields missing ─────────────────────────

SEARCH_SPARSE_RESPONSE = {
    "response": {
        "numFound": 1,
        "start": 0,
        "docs": [
            {
                "identifier": "free-talk-live-2008-09-19",
                "title": "Free Talk Live - 2008-09-19",
                "mediatype": "audio",
            }
        ],
    }
}


@pytest.mark.asyncio
async def test_search_archive_sparse_result_missing_optional_fields():
    from wayback_mcp.tools.search import search_archive
    from wayback_mcp.models import SearchResult

    with respx.mock:
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=SEARCH_SPARSE_RESPONSE)
        )
        result = await search_archive("free talk live")

    assert len(result) == 1
    r = result[0]
    assert isinstance(r, SearchResult)
    assert r.year is None
    assert r.creator is None
    assert r.subject is None
    assert r.downloads is None


# ── Cycle 7: creator as string (not list) ────────────────────────────────────

@pytest.mark.asyncio
async def test_search_archive_creator_as_string():
    from wayback_mcp.tools.search import search_archive

    response = {
        "response": {
            "numFound": 1,
            "docs": [
                {
                    "identifier": "item-123",
                    "title": "Some Book",
                    "mediatype": "texts",
                    "creator": "Single Author",
                }
            ],
        }
    }
    with respx.mock:
        respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=response))
        result = await search_archive("some book")

    assert result[0].creator == "Single Author"


@pytest.mark.asyncio
async def test_search_archive_creator_as_list():
    from wayback_mcp.tools.search import search_archive

    response = {
        "response": {
            "numFound": 1,
            "docs": [
                {
                    "identifier": "item-456",
                    "title": "Another Book",
                    "mediatype": "texts",
                    "creator": ["Author A", "Author B"],
                }
            ],
        }
    }
    with respx.mock:
        respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=response))
        result = await search_archive("another book")

    assert result[0].creator == ["Author A", "Author B"]


# ── Cycle 8: zero results ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_archive_zero_results_returns_empty_list():
    from wayback_mcp.tools.search import search_archive

    with respx.mock:
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"response": {"numFound": 0, "docs": []}})
        )
        result = await search_archive("xyzzy-no-match-ever")

    assert result == []


# ── Cycle 9: non-JSON / malformed response ────────────────────────────────────

@pytest.mark.asyncio
async def test_search_archive_non_json_returns_empty_list():
    from wayback_mcp.tools.search import search_archive

    with respx.mock:
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        result = await search_archive("bad lucene query ::::")

    assert result == []


# ── Cycle 10: request hits SEARCH_URL ────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_archive_hits_search_url():
    from wayback_mcp.tools.search import search_archive

    with respx.mock:
        route = respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"response": {"numFound": 0, "docs": []}})
        )
        await search_archive("test query")

    assert route.called
    request = route.calls.last.request
    assert "advancedsearch.php" in str(request.url)
    assert "output=json" in str(request.url)
