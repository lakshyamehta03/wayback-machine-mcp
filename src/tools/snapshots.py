from typing import List

from wayback_mcp.client.cdx import cdx_query
from wayback_mcp.models import AvailabilityResult, Snapshot, ToolError


async def check_availability(
    url: str,
    timestamp: str | None = None,
) -> AvailabilityResult | ToolError:
    """Check whether the Wayback Machine has a snapshot for the URL.

    Implemented on top of CDX (lookup_snapshots) so the whole tool surface
    shares one upstream endpoint, one rate-limit bucket, and the cookie-based
    auth routing that meaningfully raises success rate under load (#26).
    Closest-in-time semantics are preserved via CDX's closest=/sort=closest.

    Responses are cached at the HTTP layer for the cdx bucket TTL, so a
    no-timestamp lookup ("most recent snapshot") may miss a brand-new
    capture for up to that TTL.
    """
    if timestamp:
        snapshots = await lookup_snapshots(url, closest_to=timestamp, limit=1, collapse="")
    else:
        snapshots = await lookup_snapshots(url, latest=True, limit=1, collapse="")

    if isinstance(snapshots, ToolError):
        return snapshots
    if not snapshots:
        return AvailabilityResult(original_url=url, available=False)

    snap = snapshots[0]
    return AvailabilityResult(
        original_url=url,
        available=True,
        snapshot_url=snap.wayback_url,
        timestamp=snap.timestamp,
        status=snap.status_code,
    )


async def lookup_snapshots(
    url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    status_code: str | None = None,
    limit: int | None = None,
    collapse: str | None = None,
    latest: bool = False,
    closest_to: str | None = None,
) -> List[Snapshot] | ToolError:
    """Return CDX snapshots for a URL.

    `collapse` controls per-row deduplication on the CDX side:
      - None (default) → "timestamp:8" (one capture per day, the most useful
        agent default — popular URLs otherwise return one row per crawler hit)
      - "digest" → only captures whose content changed
      - "" (empty string) → no collapsing, return every capture
      - any other CDX collapse spec is passed through

    `latest=True` uses CDX's fastLatest path to return the N most recent
    captures cheaply. Cannot be combined with `from_date`/`to_date`.

    `closest_to=<ts>` orders results by proximity to that timestamp (CDX
    closest=/sort=closest). Pair with limit=1 to fetch the single nearest
    capture — same semantics as the availability endpoint, but one
    bucket-aligned request instead of two.
    """
    if latest and (from_date or to_date):
        return ToolError(
            error="'latest' cannot be combined with from_date/to_date filters."
        )
    if closest_to and (latest or from_date or to_date):
        return ToolError(
            error="'closest_to' cannot be combined with latest/from_date/to_date."
        )

    effective_collapse: str | None
    if collapse is None:
        effective_collapse = "timestamp:8"
    elif collapse == "":
        effective_collapse = None
    else:
        effective_collapse = collapse

    effective_limit = limit
    if latest:
        # CDX semantics: limit=-N → the N most recent captures (paired with
        # fastLatest=true). Default to 5 when caller didn't specify.
        n = abs(limit) if limit is not None else 5
        effective_limit = -n

    return await cdx_query(
        url=url,
        fields=["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
        from_date=from_date,
        to_date=to_date,
        status_code=status_code,
        limit=effective_limit,
        collapse=effective_collapse,
        fast_latest=latest,
        closest=closest_to,
    )
