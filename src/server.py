from mcp.server.fastmcp import FastMCP

from wayback_mcp.tools.snapshots import check_availability as _check_availability

mcp = FastMCP("wayback-mcp")


@mcp.tool()
async def check_availability(url: str, timestamp: str | None = None) -> dict:
    """Check if a URL has been archived by the Wayback Machine and return the closest snapshot."""
    result = await _check_availability(url, timestamp)
    return result.model_dump()


def main() -> None:
    mcp.run(transport="stdio")
