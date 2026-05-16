import pytest

from wayback_mcp.models import ItemMetadata
from wayback_mcp.tools.content import get_item_metadata


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_item_metadata_live_known_item():
    # Einstein relativity — always exists on IA
    result = await get_item_metadata("principleofrelat00eins")

    assert isinstance(result, ItemMetadata)
    assert result.identifier == "principleofrelat00eins"
    assert result.title is not None
    assert result.mediatype == "texts"
    assert isinstance(result.creator, list)
    assert result.file_count > 0
