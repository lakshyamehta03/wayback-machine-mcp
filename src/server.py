from mcp.server.fastmcp import FastMCP

from wayback_mcp.tools.content import get_item_metadata as _get_item_metadata
from wayback_mcp.tools.snapshots import (
    check_availability as _check_availability,
    lookup_snapshots as _lookup_snapshots,
)
from wayback_mcp.tools.search import search_archive as _search_archive
from wayback_mcp.tools.search import search_domain as _search_domain

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


@mcp.tool()
async def search_archive(
    query: str,
    mediatype: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int | None = None,
) -> list[dict] | dict:
    """Search Internet Archive collections using Lucene query syntax. Supports mediatype and year range filters."""
    result = await _search_archive(query, mediatype, year_from, year_to, limit)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return [r.model_dump() for r in result]


@mcp.tool()
async def search_domain(
    domain: str,
    from_date: str | None = None,
    to_date: str | None = None,
    status_code: str | None = None,
    limit: int | None = None,
) -> list[dict] | dict:
    """Find archived URLs under a domain or path prefix. Auto-detects matchType from input."""
    result = await _search_domain(domain, from_date, to_date, status_code, limit)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return [r.model_dump() for r in result]


@mcp.tool()
async def get_item_metadata(identifier: str) -> dict:
    """Fetch rich structured metadata for any Internet Archive item by its identifier."""
    result = await _get_item_metadata(identifier)
    return result.model_dump()


def main() -> None:
    mcp.run(transport="stdio")
