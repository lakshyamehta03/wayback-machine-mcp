import argparse
import sys

from mcp.server.fastmcp import FastMCP

from wayback_mcp.config import ia_credentials
from wayback_mcp.install import (
    CLIENTS,
    auth_setup_guide,
    clear_auth,
    install,
    pick_client_interactively,
    set_auth,
    uninstall,
)
from wayback_mcp.models import ToolError
from wayback_mcp.tools.content import (
    get_item_metadata as _get_item_metadata,
    get_snapshot_content as _get_snapshot_content,
)
from wayback_mcp.tools.snapshots import (
    check_availability as _check_availability,
    lookup_snapshots as _lookup_snapshots,
)
from wayback_mcp.tools.search import (
    search_archive as _search_archive,
    search_domain as _search_domain,
) 

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
    collapse: str | None = None,
    latest: bool = False,
) -> list:
    """Return CDX snapshots for a URL, with optional date range and status-code filter.

    The Wayback Machine often crawls the same URL many times per day; raw CDX results would return one row per crawl. `collapse` is a server-side de-duplication: adjacent rows that share the same value in the chosen field get folded into a single representative row.

    By default we collapse on the first 8 digits of the timestamp (`"timestamp:8"`), which is the YYYYMMDD prefix — i.e. **one row per day**. This is almost always what you want for "show me snapshots of this URL"; otherwise the default limit of 50 gets eaten by 50 captures from a single hour and you see nothing about the URL's history.

    Override `collapse` when you need different granularity:
    - `"digest"` — collapse on content hash, so you only see captures where the page actually *changed*
    - `"timestamp:10"` — one row per hour (first 10 digits of timestamp)
    - `""` (empty string) — disable collapsing entirely; return every capture
    - any other CDX collapse spec is passed through verbatim

    `latest=True` uses CDX's fastLatest path to return the N most recent captures cheaply (much faster than a full scan over the index). Cannot be combined with `from_date`/`to_date`."""
    result = await _lookup_snapshots(url, from_date, to_date, status_code, limit, collapse, latest)
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
    """Search Internet Archive *collections* (uploaded books, audio, video, software items) using Lucene query syntax.

    This is NOT a search over the Wayback Machine web crawl. It only returns items that someone has uploaded to archive.org as a discrete media item.

    Do NOT use this for:
    - Current news, journalism, or recent events
    - Government circulars, press releases, or official web pages
    - Wikipedia articles or any live web content
    - "What was on this website" / "what URLs are archived" — use `search_domain` or `lookup_snapshots` for those.

    Good uses: historical books, lecture recordings, archived films, software releases, podcast episodes, scanned magazines. Use Lucene fields when possible (e.g. `subject:"civil war"`, `creator:"NASA"`, `collection:librivoxaudio`)."""
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
        f"Step 1 — Decompose the topic before any tool calls.\n"
        f"Identify:\n"
        f"- 2–3 core concepts (prefer specific terms over generic ones)\n"
        f"- Implied time range, if any (e.g. 'the moon landing' → 1960–1972)\n"
        f"- Relevant disciplines, institutions, or key figures\n"
        f"Use this analysis to form distinct search queries, not just the raw topic string.\n\n"
        f"Step 2 — Search for texts (primary source type).\n"
        f"Run 2–3 `search_archive` calls with `mediatype='texts'`, each using a "
        f"different query angle drawn from Step 1. Use Lucene field operators for precision:\n"
        f"  subject:\"term\"          exact subject-tag match\n"
        f"  title:\"term\"            match in item title\n"
        f"  creator:\"name\"          by author or institution\n"
        f"  collection:NAME          scope to a collection — good ones for research:\n"
        f"                           internetarchivebooks, jstor_artsci, academic_papers\n"
        f"  term1 AND term2          require both\n"
        f"  \"exact phrase\"           phrase match\n"
        f"Example angles for 'Cold War propaganda films':\n"
        f"  query 1: subject:\"cold war\" AND subject:\"propaganda\" mediatype=texts\n"
        f"  query 2: title:\"cold war\" creator:\"US government\" mediatype=texts\n"
        f"  query 3: \"cold war\" collection:internetarchivebooks mediatype=texts\n"
        f"Use `limit=10` per call. Pass `year_from`/`year_to` when the topic implies a date range.\n\n"
        f"Step 3 — Supplement with audio or video only if clearly relevant.\n"
        f"If the topic inherently involves speech, performance, or visual media "
        f"(e.g. speeches, oral histories, documentaries), run one additional "
        f"`search_archive` call with `mediatype='audio'` or `mediatype='movies'`. "
        f"Skip this step for most research topics — text sources parse more reliably.\n\n"
        f"Step 4 — Select and enrich.\n"
        f"From all results, pick the 5 most relevant items. Prefer texts with high "
        f"download counts and titles that clearly match the topic. "
        f"Call `get_item_metadata` for each to retrieve description, creator, subject, and files.\n\n"
        f"Step 5 — Synthesise.\n"
        f"Write a research overview citing each item by identifier and title. Cover: "
        f"what each source contributes, the collective time span, key creators or "
        f"institutions, and any notable gaps. If results look sparse or off-topic, "
        f"say so and suggest a refined query rather than padding the summary.\n"
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
        "--set-auth",
        nargs="?",
        const="<pick>",
        default=None,
        metavar="CLIENT",
        dest="set_auth",
        help=(
            "Write Internet Archive S3 keys into the wayback entry of an MCP "
            "client's config. Prompts for keys interactively. Same arg semantics "
            "as --install."
        ),
    )
    parser.add_argument(
        "--clear-auth",
        nargs="?",
        const="<pick>",
        default=None,
        metavar="CLIENT",
        dest="clear_auth",
        help="Remove Internet Archive S3 keys from a client's wayback entry. Same arg semantics as --install.",
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
        help=(
            "With --install, overwrite an existing wayback entry. "
            "With --uninstall, skip the confirmation prompt for entries "
            "found under non-default key names."
        ),
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

    mutex = [
        ("--install", args.install),
        ("--uninstall", args.uninstall),
        ("--set-auth", args.set_auth),
        ("--clear-auth", args.clear_auth),
    ]
    active = [name for name, val in mutex if val is not None]
    if len(active) > 1:
        parser.error(f"{', '.join(active)} are mutually exclusive")

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
        sys.exit(uninstall(client_key, force=args.force))

    if args.set_auth is not None:
        client_key = args.set_auth
        if client_key == "<pick>":
            picked = pick_client_interactively()
            if picked is None:
                print(
                    "Cancelled. Pass a client name to skip the picker, e.g. "
                    "`--set-auth claude-desktop`. See --list-clients for options.",
                    file=sys.stderr,
                )
                sys.exit(1)
            client_key = picked.key
        sys.exit(set_auth(client_key))

    if args.clear_auth is not None:
        client_key = args.clear_auth
        if client_key == "<pick>":
            picked = pick_client_interactively()
            if picked is None:
                print(
                    "Cancelled. Pass a client name to skip the picker, e.g. "
                    "`--clear-auth claude-desktop`. See --list-clients for options.",
                    file=sys.stderr,
                )
                sys.exit(1)
            client_key = picked.key
        sys.exit(clear_auth(client_key))

    mcp.run(transport="stdio")
