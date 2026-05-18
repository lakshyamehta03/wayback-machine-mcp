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
    # CDX is empirically flaky (~85% 503/timeout at 5 rps even from a fresh
    # IP, with no per-client quota being enforced — see issue #28). Lowering
    # outbound rate doesn't fix the upstream but reduces our queue depth into
    # a degraded backend and avoids stacking retries on top of in-flight
    # failures.
    "cdx": 1.0,
    "search": 0.5,
    "metadata": 1.0,
    "content": 2.0,
}

REQUEST_TIMEOUT = 30.0  # seconds — default for content fetches
# Lightweight API endpoints (CDX, availability, search, metadata) should fail
# fast so a slow/hanging IA server doesn't stall the event loop for minutes.
REQUEST_TIMEOUTS: dict[str, float] = {
    # CDX is genuinely slow on heavily-crawled URLs (Wikipedia, major news
    # sites) and a sub-30s cap cuts off real responses mid-flight.
    "cdx": 30.0,
    "search": 10.0,
    "metadata": 10.0,
    "content": 30.0,
}
# Bumped from 3 → 5 to ride out IA's 5-15s recovery windows. Combined with
# exponential backoff in http.py the total wait budget is ~30s + per-attempt
# backoffs, which is enough to cover most observed 503 streaks.
MAX_RETRIES = 5
# Cap concurrent in-flight HTTP requests to IA. An agent can fire many parallel
# tool calls at once; without this cap we'd self-trigger cascading 429s.
MAX_CONCURRENT_REQUESTS = 4

# Circuit breaker: when this many consecutive 5xx/network failures hit a single
# rate bucket, short-circuit subsequent calls for COOLDOWN_S seconds instead of
# letting every call eat its full retry budget against a known-degraded backend.
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN_S = 30.0

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
