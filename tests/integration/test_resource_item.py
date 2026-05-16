import json

import pytest

from wayback_mcp.server import mcp


@pytest.mark.integration
@pytest.mark.asyncio
async def test_item_resource_live_known_item():
    contents = await mcp.read_resource("wayback://item/principleofrelat00eins")

    assert len(contents) == 1
    assert contents[0].mime_type == "application/json"
    payload = json.loads(contents[0].content)
    assert payload["identifier"] == "principleofrelat00eins"
    assert payload["mediatype"] == "texts"
    assert payload["title"]
    assert isinstance(payload["creator"], list) and payload["creator"]
