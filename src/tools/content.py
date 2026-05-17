from wayback_mcp.client.extractor import classify_mime, extract_html, extract_plaintext
from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_item_metadata
from wayback_mcp.config import METADATA_URL, WAYBACK_CONTENT_BASE
from wayback_mcp.models import ItemMetadata, SnapshotContent, ToolError
from wayback_mcp.tools.snapshots import check_availability, lookup_snapshots


async def get_snapshot_content(url: str, timestamp: str | None = None) -> SnapshotContent | ToolError:
    availability = await check_availability(url, timestamp)
    if isinstance(availability, ToolError):
        return availability
    if not availability.available:
        return ToolError(error=f"No archived snapshot found for '{url}'.")

    resolved_ts = availability.timestamp
    snapshot_url = availability.snapshot_url

    snapshots = await lookup_snapshots(url, from_date=resolved_ts, to_date=resolved_ts, limit=1)
    if isinstance(snapshots, ToolError):
        return snapshots

    mime_class = classify_mime(snapshots[0].mimetype) if snapshots else "html"

    if mime_class == "declined":
        mime_label = snapshots[0].mimetype if snapshots else "unknown"
        return ToolError(
            error=f"Content type '{mime_label}' is not supported for extraction. View snapshot: {snapshot_url}"
        )

    content_url = f"{WAYBACK_CONTENT_BASE}/{resolved_ts}if_/{url}"
    response = await get(content_url, "content")

    if isinstance(response, ToolError):
        return response

    result = extract_html(response.text) if mime_class == "html" else extract_plaintext(response.text)

    return SnapshotContent(
        content=result.text,
        content_type=mime_class,
        extraction_method=result.method,
        word_count=result.word_count,
        truncated=result.truncated,
        snapshot_url=snapshot_url,
        timestamp=resolved_ts,
        sparse_content_warning=(result.word_count < 500 and result.method == "body-fallback"),
    )


async def get_item_metadata(identifier: str) -> ItemMetadata | ToolError:
    response = await get(f"{METADATA_URL}/{identifier}", "metadata")

    if isinstance(response, ToolError):
        return response

    try:
        data = response.json()
    except Exception:
        return ToolError(error="Failed to parse metadata response from the Wayback Machine.")

    if not data or "error" in data:
        msg = data.get("error", f"Item '{identifier}' not found.") if data else f"Item '{identifier}' not found."
        return ToolError(error=msg)

    return parse_item_metadata(data)
