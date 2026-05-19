import re

from wayback_mcp.client.extractor import classify_mime, extract_html, extract_plaintext
from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_item_metadata
from wayback_mcp.config import METADATA_URL, WAYBACK_CONTENT_BASE
from wayback_mcp.models import ItemMetadata, SnapshotContent, ToolError


def _extract_ts(url: str) -> str | None:
    """Parse a 14-digit Wayback timestamp out of a web.archive.org URL."""
    m = re.search(r"/web/(\d{14})", url)
    return m.group(1) if m else None


async def get_snapshot_content(url: str, timestamp: str | None = None) -> SnapshotContent | ToolError:
    ts = timestamp or ""
    content_url = f"{WAYBACK_CONTENT_BASE}/{ts}if_/{url}"

    response = await get(content_url, "content")
    if isinstance(response, ToolError):
        return response
    if response.status_code == 404:
        return ToolError(error=f"No archived snapshot found for '{url}'.")

    # Wayback redirects to the nearest captured timestamp — parse it from the
    # final URL so we report the real capture time, not the requested ts.
    resolved_ts = _extract_ts(str(response.url)) or timestamp or ""
    snapshot_url = f"{WAYBACK_CONTENT_BASE}/{resolved_ts}/{url}"

    content_type = response.headers.get("content-type", "")
    mime_class = classify_mime(content_type)

    if mime_class == "declined":
        bare_type = content_type.split(";")[0].strip()
        return ToolError(
            error=f"Content type '{bare_type}' is not supported for extraction. View snapshot: {snapshot_url}"
        )

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
