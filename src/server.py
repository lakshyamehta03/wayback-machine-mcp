from mcp.server.fastmcp import FastMCP

from wayback_mcp.models import ToolError
from wayback_mcp.tools.content import get_item_metadata as _get_item_metadata
from wayback_mcp.tools.content import get_snapshot_content as _get_snapshot_content
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
async def get_snapshot_content(url: str, timestamp: str | None = None) -> dict:
    """Fetch and extract text content from an archived web page. Returns extracted text, word count, and extraction metadata."""
    result = await _get_snapshot_content(url, timestamp)
    return result.model_dump()


@mcp.tool()
async def get_item_metadata(identifier: str) -> dict:
    """Fetch rich structured metadata for any Internet Archive item by its identifier."""
    result = await _get_item_metadata(identifier)
    return result.model_dump()


@mcp.prompt()
def research_topic(
    topic: str,
    year_from: int | None = None,
    year_to: int | None = None,
    max_items: int = 5,
) -> str:
    """Research a topic across Internet Archive collections and synthesise an overview."""
    year_clause = ""
    if year_from is not None or year_to is not None:
        year_clause = f" Restrict to the year range {year_from}–{year_to}."
    return (
        f"Research the topic: {topic!r}.{year_clause}\n\n"
        f"Workflow:\n"
        f"1. Call `search_archive` with query={topic!r} once per mediatype in "
        f"['texts', 'audio', 'movies'], passing year_from={year_from} and "
        f"year_to={year_to}, limit={max_items}.\n"
        f"2. From the combined results, pick the {max_items} most relevant items "
        f"(prefer high download counts and titles that clearly match the topic).\n"
        f"3. For each chosen item, call `get_item_metadata` with its identifier to "
        f"enrich the entry with description, creator, subject, and file information.\n"
        f"4. Synthesise a topic overview citing each item by identifier and title, "
        f"noting media diversity, time span, and notable creators or subjects.\n"
    )


@mcp.prompt()
def track_site_changes(
    url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    sample_size: int = 5,
) -> str:
    """Narrate how an archived web page changed over time using sampled snapshots."""
    range_clause = f" between {from_date} and {to_date}" if (from_date or to_date) else ""
    return (
        f"Trace how {url} changed over time{range_clause}.\n\n"
        f"Workflow:\n"
        f"1. Call `lookup_snapshots` with url={url!r}, from_date={from_date!r}, "
        f"to_date={to_date!r} to enumerate all available captures.\n"
        f"2. From that list, sample {sample_size} snapshots: always include the "
        f"first and last, and pick the remaining evenly-spaced across the middle. "
        f"Do NOT fetch every snapshot — sampling keeps token usage bounded.\n"
        f"3. For each sampled snapshot, call `get_snapshot_content` with the URL and "
        f"the snapshot's timestamp to extract its text.\n"
        f"4. Compare the extracted content across timestamps and narrate what "
        f"changed: structural shifts, content rewrites, additions, removals, tone. "
        f"Reference each snapshot by its timestamp.\n"
    )


@mcp.prompt()
def audit_link_rot(urls: str) -> str:
    """Audit a list of URLs for link rot, surfacing archived alternatives."""
    parsed = [u.strip() for u in urls.replace(",", "\n").splitlines() if u.strip()]
    url_block = "\n".join(f"- {u}" for u in parsed)
    return (
        f"Audit the following URLs for link rot:\n{url_block}\n\n"
        f"Workflow:\n"
        f"1. Iterate over each URL above and call `check_availability(url)` once per "
        f"URL. Do NOT attempt a batch call — each URL gets its own request.\n"
        f"2. Classify each URL: live (currently resolvable on the open web is out of "
        f"scope here — treat 'available in the Wayback Machine' as the recoverable "
        f"signal), recoverable (Wayback has a snapshot), or unrecoverable (no "
        f"snapshot at all).\n"
        f"3. Summarise the results: which links are dead, and for the recoverable "
        f"ones, list the snapshot_url and timestamp returned by `check_availability` "
        f"so the user can substitute archived copies for broken links.\n"
    )


@mcp.resource("wayback://item/{identifier}", mime_type="application/json")
async def item_resource(identifier: str) -> str:
    """Full Internet Archive item metadata as JSON, addressed by identifier."""
    result = await _get_item_metadata(identifier)
    if isinstance(result, ToolError):
        raise ValueError(result.error)
    return result.model_dump_json()


def main() -> None:
    mcp.run(transport="stdio")
