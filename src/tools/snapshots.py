from typing import List

from wayback_mcp.client.cdx import cdx_query
from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_availability
from wayback_mcp.config import AVAILABILITY_URL
from wayback_mcp.models import AvailabilityResult, Snapshot, ToolError


async def check_availability(
    url: str,
    timestamp: str | None = None,
) -> AvailabilityResult | ToolError:
    """Check whether the Wayback Machine has a snapshot for the URL.

    Responses are cached at the HTTP layer for the cdx bucket TTL, so a
    no-timestamp lookup ("most recent snapshot") may miss a brand-new
    capture for up to that TTL.
    """
    params: dict[str, str] = {"url": url}
    if timestamp:
        params["timestamp"] = timestamp

    response = await get(AVAILABILITY_URL, "cdx", params=params)

    if isinstance(response, ToolError):
        return response

    try:
        data = response.json()
    except Exception:
        return ToolError(error="Failed to parse availability response from the Wayback Machine.")

    return parse_availability(url, data)


async def lookup_snapshots(
    url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    status_code: str | None = None,
    limit: int | None = None,
) -> List[Snapshot] | ToolError:
    return await cdx_query(
        url=url,
        fields=["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
        from_date=from_date,
        to_date=to_date,
        status_code=status_code,
        limit=limit,
    )
