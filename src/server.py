import argparse
import sys

from mcp.server.fastmcp import FastMCP

from wayback_mcp.config import ia_credentials
from wayback_mcp.install import (
    CLIENTS,
    auth_setup_guide,
    install,
    pick_client_interactively,
    uninstall,
)
from wayback_mcp.models import ToolError
from wayback_mcp.tools.content import get_item_metadata as _get_item_metadata
from wayback_mcp.tools.content import get_snapshot_content as _get_snapshot_content
from wayback_mcp.tools.snapshots import (
    check_availability as _check_availability,
    lookup_snapshots as _lookup_snapshots,
)
from wayback_mcp.tools.search import search_archive as _search_archive
from wayback_mcp.tools.search import search_domain as _search_domain

mcp = FastMCP("wayback")


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
def research_topic(topic: str) -> str:
    """Research a topic across Internet Archive collections and synthesise an overview.

    Takes a single free-text `topic` argument. Time ranges and sample sizes
    are interpreted from the topic phrasing by the model (e.g. "the moon
    landing in the 1960s" → year range 1960–1969).
    """
    return (
        f"Research the topic: {topic!r}.\n\n"
        f"Workflow:\n"
        f"1. Call `search_archive` with a query derived from the topic above, "
        f"once per mediatype in ['texts', 'audio', 'movies']. If the topic "
        f"implies a time range, pass `year_from` / `year_to` accordingly; "
        f"otherwise omit them. Use `limit=5` per call.\n"
        f"2. From the combined results, pick the 5 most relevant items "
        f"(prefer high download counts and titles that clearly match the topic).\n"
        f"3. For each chosen item, call `get_item_metadata` with its identifier to "
        f"enrich the entry with description, creator, subject, and file information.\n"
        f"4. Synthesise a topic overview citing each item by identifier and title, "
        f"noting media diversity, time span, and notable creators or subjects.\n"
    )


@mcp.prompt()
def track_site_changes(url: str) -> str:
    """Narrate how an archived web page changed over time using sampled snapshots.

    Takes a single free-text `url` argument. Date ranges are interpreted from
    the surrounding context by the model when present.
    """
    return (
        f"Trace how {url} changed over time.\n\n"
        f"Workflow:\n"
        f"1. Call `lookup_snapshots` with url={url!r} to enumerate available "
        f"captures. If the user's request implies a date range, pass "
        f"`from_date` / `to_date` (YYYYMMDD) accordingly.\n"
        f"2. From that list, sample 5 snapshots: always include the first and "
        f"last, and pick the remaining evenly-spaced across the middle. Do NOT "
        f"fetch every snapshot — sampling keeps token usage bounded.\n"
        f"3. For each sampled snapshot, call `get_snapshot_content` with the URL "
        f"and the snapshot's timestamp to extract its text.\n"
        f"4. Compare the extracted content across timestamps and narrate what "
        f"changed: structural shifts, content rewrites, additions, removals, "
        f"tone. Reference each snapshot by its timestamp.\n"
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


@mcp.prompt()
def setup_authentication() -> str:
    """Walk the user through configuring Internet Archive API keys for higher rate limits."""
    if ia_credentials() is not None:
        return (
            "The user already has Internet Archive credentials configured. Tell them "
            "verbatim:\n\n"
            "> ✓ Authentication credentials detected. `WAYBACK_MCP_IA_ACCESS_KEY` and "
            "`WAYBACK_MCP_IA_SECRET_KEY` are both set in the server's environment, so "
            "every outbound Internet Archive request is authenticated and benefits from "
            "the higher rate-limit ceiling. No further action needed."
        )
    return (
        "The user needs to configure Internet Archive API keys. Your job is to "
        "show them the guide below **exactly as written**, including the JSON code "
        "block and every URL. Do not summarise, paraphrase, or omit the code block — "
        "the user needs to paste it. After displaying the guide, optionally offer to "
        "answer follow-up questions, but do not skip any part of the guide itself.\n\n"
        "---\n\n"
        f"{auth_setup_guide()}"
    )


@mcp.resource("wayback://item/{identifier}", mime_type="application/json")
async def item_resource(identifier: str) -> str:
    """Full Internet Archive item metadata as JSON, addressed by identifier."""
    result = await _get_item_metadata(identifier)
    if isinstance(result, ToolError):
        raise ValueError(result.error)
    return result.model_dump_json()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-server-wayback",
        description="MCP server for the Internet Archive's Wayback Machine.",
    )
    parser.add_argument(
        "--install",
        nargs="?",
        const="<pick>",
        default=None,
        metavar="CLIENT",
        help=(
            "Add this server to an MCP client's config. Pass a client key (see "
            "--list-clients), or omit the value to pick interactively."
        ),
    )
    parser.add_argument(
        "--uninstall",
        nargs="?",
        const="<pick>",
        default=None,
        metavar="CLIENT",
        help="Remove this server from an MCP client's config. Same arg semantics as --install.",
    )
    parser.add_argument(
        "--list-clients",
        action="store_true",
        help="Print the supported client keys for --install / --uninstall and exit.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the installed version and exit.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --install, overwrite an existing wayback entry.",
    )
    args = parser.parse_args()

    if args.version:
        from importlib.metadata import PackageNotFoundError, version
        try:
            print(version("mcp-server-wayback"))
        except PackageNotFoundError:
            print("unknown (package metadata not found)")
        sys.exit(0)

    if args.list_clients:
        for c in CLIENTS:
            print(f"  {c.key:24s}  {c.label}")
        sys.exit(0)

    if args.install is not None and args.uninstall is not None:
        parser.error("--install and --uninstall are mutually exclusive")

    if args.install is not None:
        client_key = args.install
        if client_key == "<pick>":
            picked = pick_client_interactively()
            if picked is None:
                print(
                    "Cancelled. Pass a client name to skip the picker, e.g. "
                    "`--install claude-desktop`. See --list-clients for options.",
                    file=sys.stderr,
                )
                sys.exit(1)
            client_key = picked.key
        sys.exit(install(client_key, force=args.force))

    if args.uninstall is not None:
        client_key = args.uninstall
        if client_key == "<pick>":
            picked = pick_client_interactively()
            if picked is None:
                print(
                    "Cancelled. Pass a client name to skip the picker, e.g. "
                    "`--uninstall claude-desktop`. See --list-clients for options.",
                    file=sys.stderr,
                )
                sys.exit(1)
            client_key = picked.key
        sys.exit(uninstall(client_key))

    mcp.run(transport="stdio")
