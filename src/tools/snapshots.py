from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_availability
from wayback_mcp.config import AVAILABILITY_URL
from wayback_mcp.models import AvailabilityResult, ToolError


async def check_availability(
    url: str,
    timestamp: str | None = None,
) -> AvailabilityResult | ToolError:
    params: dict[str, str] = {"url": url}
    if timestamp:
        params["timestamp"] = timestamp

    response = await get(AVAILABILITY_URL, "cdx", params=params)

    if response.status_code == 429:
        return ToolError(error="Rate limited by the Wayback Machine. Try again later.")

    try:
        data = response.json()
    except Exception:
        return ToolError(error="Failed to parse availability response from the Wayback Machine.")

    return parse_availability(url, data)
