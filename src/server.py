from mcp.server.fastmcp import FastMCP

from wayback_mcp.tools.snapshots import (
    check_availability as _check_availability,
    lookup_snapshots as _lookup_snapshots,
)

mcp = FastMCP("wayback-mcp")


@mcp.tool()
async def check_availability(url: str, timestamp: str | None = None) -> dict:
    """Check if a URL has been archived by the Wayback Machine and return the closest snapshot."""
    result = await _check_availability(url, timestamp)
    return result.model_dump()


@mcp.tool()
async def lookup_snapshots(
    url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    status_code: str | None = None,
    limit: int | None = None,
) -> list:
    """Return all CDX snapshots for a URL, with optional date range and status-code filter."""
    result = await _lookup_snapshots(url, from_date, to_date, status_code, limit)
    if hasattr(result, "model_dump"):
        return [result.model_dump()]
    return [s.model_dump() for s in result]


def main() -> None:
    mcp.run(transport="stdio")
