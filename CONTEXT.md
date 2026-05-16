# wayback-mcp — Domain Context

## Glossary

| Term | Definition |
|---|---|
| Snapshot | A single archived capture of a URL at a specific timestamp in `YYYYMMDDHHMMSS` format |
| CDX | Wayback Machine's index API; returns array-of-arrays where `raw[0]` is always the header row |
| Availability API | Lightweight endpoint (`/wayback/available`) to check whether a URL is archived and find the nearest snapshot |
| Rate key | Named key identifying which token bucket to acquire from (`"cdx"`, `"search"`, `"metadata"`) |
| Token bucket | Async rate-limiting primitive: bursts up to `capacity`, then enforces steady-state `rate` (tokens/sec) |
| `ToolError` | Structured return value for expected failures (not-found, unsupported type, rate-limited); unexpected failures raise exceptions |
| `if_` modifier | Wayback URL suffix that suppresses the injected toolbar: `/web/{timestamp}if_/{url}` |
| Closest | The `archived_snapshots.closest` field — only present when a snapshot was found; never access directly |

## Architectural invariants

- All IA requests go through `client/http.py` → `client/rate_limiter.py`; tool files never make HTTP calls directly
- Pydantic models are centralized in `models.py`; tool files and `parsers.py` import from there
- Expected failures return `ToolError`; unexpected failures raise exceptions (MCP SDK converts to protocol errors)
- CDX: `raw[0]` is always the header row — data starts at `raw[1:]`; all field values are strings, not ints
- `.archived_snapshots` is `{}` (empty dict, not `null`) when a URL has no archive — always guard: `data.get("archived_snapshots", {}).get("closest")`

## Live API behaviour (verified May 2026)

- `check_availability("bbc.com", timestamp="20050101")` returns `archived_snapshots: {}` — the historical snapshot no longer resolves via this endpoint; use `"archive.org"` as the integration-test baseline for an always-archived URL
- CDX empty date ranges may return a non-JSON error string — always catch `JSONDecodeError` and return `[]`
- `Availability API`: `"available"` is a boolean, not a string; `"status"` is the HTTP status of the archived page, not of this API call

## Implementation progress

### Issue #1 — Tracer bullet: `check_availability` (done)

Built the full foundational stack end-to-end:

- `pyproject.toml` with entry point `wayback-mcp = "wayback_mcp.server:main"`
- Async token-bucket rate limiter with per-key `Retry-After` backoff
- `httpx.AsyncClient` wrapper with User-Agent injected at the client level
- `check_availability` exercising every layer: rate limiter → HTTP client → parser → `AvailabilityResult`
- 5 unit tests (respx mocks) + 2 integration tests (live IA)

**Learnings:**
- Live `bbc.com` + historical timestamp no longer returns a snapshot as of May 2026; integration tests should target `archive.org` itself
- Token bucket lock is held during `asyncio.sleep` — correct for sequential rate limiting but would serialize concurrent callers (acceptable for v1 MCP server)
