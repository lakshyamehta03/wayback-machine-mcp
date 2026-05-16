import pytest
import respx
import httpx

from wayback_mcp.tools.content import get_item_metadata
from wayback_mcp.models import ItemMetadata, ToolError

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
