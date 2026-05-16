from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_item_metadata
from wayback_mcp.config import METADATA_URL
from wayback_mcp.models import ItemMetadata, ToolError


async def get_item_metadata(identifier: str) -> ItemMetadata | ToolError:
    response = await get(f"{METADATA_URL}/{identifier}", "metadata")

    if response.status_code == 429:
        return ToolError(error="Rate limited by the Wayback Machine. Try again later.")

    try:
        data = response.json()
    except Exception:
        return ToolError(error="Failed to parse metadata response from the Wayback Machine.")

    if not data or "error" in data:
        msg = data.get("error", f"Item '{identifier}' not found.") if data else f"Item '{identifier}' not found."
        return ToolError(error=msg)

    return parse_item_metadata(data)
