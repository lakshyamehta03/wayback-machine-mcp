from wayback_mcp.client.extractor import classify_mime, extract_html, extract_plaintext
from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_item_metadata
from wayback_mcp.config import METADATA_URL
from wayback_mcp.models import ItemMetadata, SnapshotContent, ToolError
from wayback_mcp.tools.snapshots import lookup_snapshots


async def get_snapshot_content(url: str, timestamp: str | None = None) -> SnapshotContent | ToolError:
    if timestamp:
        snapshots = await lookup_snapshots(url, closest_to=timestamp, limit=1, collapse="")
    else:
        snapshots = await lookup_snapshots(url, latest=True, limit=1, collapse="")

    if isinstance(snapshots, ToolError):
        return snapshots
    if not snapshots:
        return ToolError(error=f"No archived snapshot found for '{url}'.")

    snap = snapshots[0]
    snapshot_url = snap.wayback_url
    mime_class = classify_mime(snap.mimetype)

    if mime_class == "declined":
        return ToolError(
            error=f"Content type '{snap.mimetype}' is not supported for extraction. View snapshot: {snapshot_url}"
        )

    response = await get(snap.content_url, "content")

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
        timestamp=snap.timestamp,
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
