from typing import List, Optional, Union
from pydantic import BaseModel


class AvailabilityResult(BaseModel):
    original_url: str
    available: bool
    snapshot_url: Optional[str] = None
    timestamp: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class Snapshot(BaseModel):
    timestamp: str
    original_url: str
    status_code: str
    mimetype: str
    digest: Optional[str] = None
    length: Optional[str] = None

    @property
    def wayback_url(self) -> str:
        return f"https://web.archive.org/web/{self.timestamp}/{self.original_url}"

    @property
    def content_url(self) -> str:
        return f"https://web.archive.org/web/{self.timestamp}if_/{self.original_url}"


class DomainUrl(BaseModel):
    url: str
    timestamp: str
    status_code: str
    mimetype: str


class SearchResult(BaseModel):
    identifier: str
    title: str
    mediatype: str
    year: Optional[Union[int, str]] = None
    creator: Optional[Union[str, List[str]]] = None
    subject: Optional[Union[str, List[str]]] = None
    downloads: Optional[int] = None


class ItemMetadata(BaseModel):
    identifier: str
    title: Optional[str] = None
    creator: Optional[Union[str, List[str]]] = None
    subject: Optional[Union[str, List[str]]] = None
    year: Optional[str] = None
    mediatype: Optional[str] = None
    description: Optional[Union[str, List[str]]] = None
    downloads: Optional[int] = None
    item_size: Optional[int] = None
    file_count: int = 0
    files: List[dict] = []


class SnapshotContent(BaseModel):
    content: Optional[str]
    content_type: str  # "html" | "plain" | "declined"
    extraction_method: Optional[str]
    word_count: Optional[int]
    truncated: bool
    snapshot_url: str
    timestamp: str
    sparse_content_warning: bool


class ToolError(BaseModel):
    error: str


def rate_limited_error(retry_after: str | int | float) -> "ToolError":
    """Build the standard 429 ToolError, appending an auth-setup hint when unconfigured.

    When keys aren't configured, the hint includes the full claude_desktop_config.json
    snippet inline. This is verbose, but it survives any summarisation the calling
    agent might do when relaying the error to the user — the JSON block lands
    intact even if surrounding prose gets rewritten.
    """
    from wayback_mcp.config import ia_credentials
    from wayback_mcp.install import AUTH_CONFIG_SNIPPET

    msg = f"Rate limited by the Wayback Machine. Retry after {retry_after}s."
    if ia_credentials() is None:
        msg += (
            "\n\nFree Internet Archive API keys raise the rate-limit ceiling and "
            "remove these errors. Tell the user verbatim, including the JSON block:"
            "\n\n"
            "1. Get keys at https://archive.org/account/s3.php (free archive.org "
            "account required).\n"
            "2. Open `claude_desktop_config.json` (macOS: "
            "`~/Library/Application Support/Claude/claude_desktop_config.json`) and "
            "set the wayback server entry to:\n\n"
            f"{AUTH_CONFIG_SNIPPET}\n\n"
            "3. Restart Claude Desktop. Or run the `setup_authentication` prompt for "
            "the full walkthrough."
        )
    return ToolError(error=msg)
