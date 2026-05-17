import os
import sys

AVAILABILITY_URL = "https://archive.org/wayback/available"
CDX_URL = "http://web.archive.org/cdx/search/cdx"
SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata"

USER_AGENT = f"WaybackMCP/1.0 Python/{sys.version_info.major}.{sys.version_info.minor}"

# Tokens per second per endpoint group
WAYBACK_CONTENT_BASE = "https://web.archive.org/web"

RATE_LIMITS: dict[str, float] = {
    "cdx": 2.0,
    "search": 0.5,
    "metadata": 1.0,
    "content": 2.0,
}

REQUEST_TIMEOUT = 30.0  # seconds — default for content fetches
# Lightweight API endpoints (CDX, availability, search, metadata) should fail
# fast so a slow/hanging IA server doesn't stall the event loop for minutes.
REQUEST_TIMEOUTS: dict[str, float] = {
    "cdx": 10.0,
    "search": 10.0,
    "metadata": 10.0,
    "content": 30.0,
}
MAX_RETRIES = 3
# Cap concurrent in-flight HTTP requests to IA. An agent can fire many parallel
# tool calls at once; without this cap we'd self-trigger cascading 429s.
MAX_CONCURRENT_REQUESTS = 4

CDX_MAX_RESULTS = 50
SEARCH_MAX_RESULTS = 50

CACHE_MAX_ENTRIES = 256
CACHE_TTLS: dict[str, float] = {
    "metadata": 24 * 60 * 60,
    "content": 24 * 60 * 60,
    "cdx": 60 * 60,
    "search": 15 * 60,
}


def ia_credentials() -> tuple[str, str] | None:
    """Return (access_key, secret_key) if both IA S3 keys are configured, else None.

    Read at call time so tests can use monkeypatch.setenv without reload tricks.
    """
    access = os.environ.get("WAYBACK_MCP_IA_ACCESS_KEY")
    secret = os.environ.get("WAYBACK_MCP_IA_SECRET_KEY")
    if access and secret:
        return access, secret
    return None
