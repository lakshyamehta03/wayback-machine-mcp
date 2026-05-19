import pytest
import respx
import httpx

from wayback_mcp.tools.content import get_item_metadata, get_snapshot_content
from wayback_mcp.models import ItemMetadata, SnapshotContent, ToolError

METADATA_URL = "https://archive.org/metadata"

RICH_ITEM_RESPONSE = {
    "metadata": {
        "identifier": "principleofrelat00eins",
        "title": "The principle of relativity; original papers",
        "creator": [
            "Einstein, Albert, 1879-1955",
            "Minkowski, H. (Hermann), 1864-1909",
        ],
        "mediatype": "texts",
        "subject": "Relativity (Physics)",
        "year": "1920",
        "description": "3 p. l., xxiii, 186 p. 22 cm",
        "collection": ["mitlibraries", "greatbooks"],
    },
    "item": {},
    "files_count": 26,
    "files_sample": [
        {"name": "__ia_thumb.jpg", "source": "original", "size": "11635", "format": "Item Tile"},
        {"name": "principleofrelat00eins.djvu", "source": "derivative", "size": "9439156", "format": "DjVu"},
    ],
}

SPARSE_ITEM_RESPONSE = {
    "metadata": {
        "identifier": "gov.uscourts.pawb.359164",
        "title": "Kincaid v. Real Time Solutions",
        "mediatype": "texts",
        "collection": ["usfederalcourts"],
    },
    "item": {},
    "files_count": 5,
    "files_sample": [
        {"name": "docket.json", "source": "original", "size": "8766", "format": "JSON"},
    ],
}


@pytest.mark.asyncio
async def test_get_item_metadata_rich_item():
    with respx.mock:
        respx.get(f"{METADATA_URL}/principleofrelat00eins").mock(
            return_value=httpx.Response(200, json=RICH_ITEM_RESPONSE)
        )
        result = await get_item_metadata("principleofrelat00eins")

    assert isinstance(result, ItemMetadata)
    assert result.identifier == "principleofrelat00eins"
    assert result.title == "The principle of relativity; original papers"
    assert result.mediatype == "texts"
    assert result.year == "1920"
    assert result.creator == ["Einstein, Albert, 1879-1955", "Minkowski, H. (Hermann), 1864-1909"]
    assert result.subject == ["Relativity (Physics)"]
    assert result.file_count == 2
    assert len(result.files) == 2


@pytest.mark.asyncio
async def test_get_item_metadata_sparse_item_empty_item_block():
    with respx.mock:
        respx.get(f"{METADATA_URL}/gov.uscourts.pawb.359164").mock(
            return_value=httpx.Response(200, json=SPARSE_ITEM_RESPONSE)
        )
        result = await get_item_metadata("gov.uscourts.pawb.359164")

    assert isinstance(result, ItemMetadata)
    assert result.identifier == "gov.uscourts.pawb.359164"
    assert result.downloads is None
    assert result.item_size is None
    assert result.file_count == 1
    assert result.creator is None
    assert result.subject is None


@pytest.mark.asyncio
async def test_get_item_metadata_not_found_empty_dict():
    with respx.mock:
        respx.get(f"{METADATA_URL}/does-not-exist").mock(
            return_value=httpx.Response(200, json={})
        )
        result = await get_item_metadata("does-not-exist")

    assert isinstance(result, ToolError)
    assert "does-not-exist" in result.error


@pytest.mark.asyncio
async def test_get_item_metadata_str_creator_and_subject_normalized_to_list():
    response = {
        "metadata": {
            "identifier": "someitem",
            "title": "Some Item",
            "mediatype": "texts",
            "creator": "Single Author",
            "subject": "Single Subject",
        },
        "item": {},
        "files_sample": [],
    }
    with respx.mock:
        respx.get(f"{METADATA_URL}/someitem").mock(
            return_value=httpx.Response(200, json=response)
        )
        result = await get_item_metadata("someitem")

    assert isinstance(result, ItemMetadata)
    assert result.creator == ["Single Author"]
    assert result.subject == ["Single Subject"]


@pytest.mark.asyncio
async def test_get_item_metadata_not_found_error_field():
    with respx.mock:
        respx.get(f"{METADATA_URL}/does-not-exist").mock(
            return_value=httpx.Response(200, json={"error": "Couldn't locate item 'does-not-exist'"})
        )
        result = await get_item_metadata("does-not-exist")

    assert isinstance(result, ToolError)
    assert "does-not-exist" in result.error


@pytest.mark.asyncio
async def test_get_item_metadata_files_missing_size_does_not_crash():
    response = {
        "metadata": {
            "identifier": "someitem",
            "title": "Some Item",
            "mediatype": "texts",
        },
        "item": {},
        "files_sample": [
            {"name": "nosize.pdf", "source": "original", "format": "PDF"},
            {"name": "withsize.pdf", "source": "original", "size": "12345", "format": "PDF"},
        ],
    }
    with respx.mock:
        respx.get(f"{METADATA_URL}/someitem").mock(
            return_value=httpx.Response(200, json=response)
        )
        result = await get_item_metadata("someitem")

    assert isinstance(result, ItemMetadata)
    assert result.file_count == 2
    assert result.files[0]["name"] == "nosize.pdf"
    assert "size" not in result.files[0]
    assert result.files[1]["size"] == "12345"


# ---------------------------------------------------------------------------
# get_snapshot_content tests
# ---------------------------------------------------------------------------

CDX_URL = "http://web.archive.org/cdx/search/cdx"
_TARGET_URL = "https://example.com/page"
_TIMESTAMP = "20231015120000"
_SNAPSHOT_URL = f"https://web.archive.org/web/{_TIMESTAMP}/{_TARGET_URL}"
_CONTENT_URL = f"https://web.archive.org/web/{_TIMESTAMP}if_/{_TARGET_URL}"


def _cdx_response(mimetype: str) -> list:
    return [
        ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
        [_TIMESTAMP, _TARGET_URL, mimetype, "200", "SHA1:ABC", "9999"],
    ]


_CDX_EMPTY: list = [["timestamp", "original", "mimetype", "statuscode", "digest", "length"]]


@pytest.mark.asyncio
async def test_get_snapshot_content_html_main():
    html = "<html><body><main>" + "word " * 250 + "</main></body></html>"
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/html")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=html))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, SnapshotContent)
    assert result.content_type == "html"
    assert result.extraction_method == "main"
    assert result.snapshot_url == _SNAPSHOT_URL
    assert result.timestamp == _TIMESTAMP
    assert result.word_count == 250
    assert result.truncated is False
    assert result.sparse_content_warning is False


@pytest.mark.asyncio
async def test_get_snapshot_content_html_article():
    html = "<html><body><article>" + "word " * 250 + "</article></body></html>"
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/html")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=html))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, SnapshotContent)
    assert result.extraction_method == "article"


@pytest.mark.asyncio
async def test_get_snapshot_content_html_body_fallback():
    # No semantic container — forces body-fallback
    html = "<html><body><div>" + "word " * 600 + "</div></body></html>"
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/html")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=html))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, SnapshotContent)
    assert result.extraction_method == "body-fallback"
    assert result.sparse_content_warning is False


@pytest.mark.asyncio
async def test_get_snapshot_content_plaintext_capped():
    long_text = "a" * 11000
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/plain")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=long_text))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, SnapshotContent)
    assert result.content_type == "plain"
    assert result.extraction_method == "plain-text"
    assert result.truncated is True
    assert len(result.content) == 10000


@pytest.mark.asyncio
async def test_get_snapshot_content_pdf_declined():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("application/pdf")))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, ToolError)
    assert "application/pdf" in result.error
    assert _SNAPSHOT_URL in result.error


@pytest.mark.asyncio
async def test_get_snapshot_content_image_declined():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("image/jpeg")))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, ToolError)
    assert "image/jpeg" in result.error
    assert _SNAPSHOT_URL in result.error


@pytest.mark.asyncio
async def test_get_snapshot_content_unavailable_url():
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_CDX_EMPTY))
        result = await get_snapshot_content("https://example.com/never-archived")

    assert isinstance(result, ToolError)
    assert "never-archived" in result.error


@pytest.mark.asyncio
async def test_get_snapshot_content_malformed_html():
    malformed = "<html><body><main><p>Some content" + " word" * 250  # unclosed tags
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/html")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=malformed))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, SnapshotContent)
    assert result.content is not None


@pytest.mark.asyncio
async def test_get_snapshot_content_sparse_content_warning():
    # 300 words, no semantic container → body-fallback + sparse warning
    html = "<html><body><div>" + "word " * 300 + "</div></body></html>"
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/html")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=html))
        result = await get_snapshot_content(_TARGET_URL)

    assert isinstance(result, SnapshotContent)
    assert result.extraction_method == "body-fallback"
    assert result.word_count < 500
    assert result.sparse_content_warning is True


@pytest.mark.asyncio
async def test_get_snapshot_content_passes_closest_to_when_timestamp_given():
    # Regression guard: ensure the timestamp arg flows through to CDX as
    # closest=<ts>&sort=closest, not as a from/to range that would only match
    # exact-second snapshots.
    html = "<html><body><main>" + "word " * 100 + "</main></body></html>"
    with respx.mock:
        respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=_cdx_response("text/html")))
        respx.get(_CONTENT_URL).mock(return_value=httpx.Response(200, text=html))
        result = await get_snapshot_content(_TARGET_URL, timestamp="20230101")
        cdx_urls = [str(c.request.url) for c in respx.calls if CDX_URL in str(c.request.url)]

    assert isinstance(result, SnapshotContent)
    assert cdx_urls, "expected at least one CDX call"
    assert "closest=20230101" in cdx_urls[0]
    assert "sort=closest" in cdx_urls[0]
