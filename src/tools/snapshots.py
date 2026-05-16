from typing import List

from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_availability, parse_cdx
from wayback_mcp.config import AVAILABILITY_URL, CDX_MAX_RESULTS, CDX_URL
from wayback_mcp.models import AvailabilityResult, Snapshot, ToolError, rate_limited_error


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

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "5")
        return rate_limited_error(retry_after)

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
    params: dict[str, str] = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,digest,length",
        "limit": str(limit if limit is not None else CDX_MAX_RESULTS),
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if status_code:
        params["filter"] = f"statuscode:{status_code}"

    response = await get(CDX_URL, "cdx", params=params)

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "5")
        return rate_limited_error(retry_after)

    try:
        raw = response.json()
    except Exception:
        return []

    return parse_cdx(raw)
