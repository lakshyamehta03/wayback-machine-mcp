import json

import httpx
import pytest
import respx

from wayback_mcp.server import mcp

METADATA_URL = "https://archive.org/metadata"

RICH_ITEM_RESPONSE = {
    "metadata": {
        "identifier": "principleofrelat00eins",
        "title": "The principle of relativity; original papers",
        "creator": ["Einstein, Albert, 1879-1955"],
        "mediatype": "texts",
        "year": "1920",
    },
    "item": {},
    "files_sample": [
        {"name": "x.djvu", "source": "derivative", "size": "9", "format": "DjVu"},
    ],
}


@pytest.mark.asyncio
async def test_item_resource_returns_metadata_as_json():
    with respx.mock:
        respx.get(f"{METADATA_URL}/principleofrelat00eins").mock(
            return_value=httpx.Response(200, json=RICH_ITEM_RESPONSE)
        )
        contents = await mcp.read_resource("wayback://item/principleofrelat00eins")

    assert len(contents) == 1
    payload = json.loads(contents[0].content)
    assert payload["identifier"] == "principleofrelat00eins"
    assert payload["title"] == "The principle of relativity; original papers"
    assert payload["mediatype"] == "texts"
    assert payload["year"] == "1920"
    assert payload["creator"] == ["Einstein, Albert, 1879-1955"]
    assert contents[0].mime_type == "application/json"


@pytest.mark.asyncio
async def test_item_resource_unknown_identifier_raises_with_useful_message():
    with respx.mock:
        respx.get(f"{METADATA_URL}/does-not-exist").mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(Exception) as exc_info:
            await mcp.read_resource("wayback://item/does-not-exist")

    assert "does-not-exist" in str(exc_info.value)
