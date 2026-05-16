# PRD: wayback-mcp

**Status:** Ready for implementation
**Version:** 1.0
**Date:** May 2026

---

## Problem Statement

Researchers, journalists, developers, and archivists want to query the Internet Archive's Wayback Machine and broader archive.org collections from within an AI assistant — but today they must leave the conversation, navigate the IA website manually, and copy-paste results back. The only existing MCP implementation (Mearman's Node.js server) covers four basic Wayback operations and has no topic-based search, no content extraction, no metadata access, and requires Node.js infrastructure that many users don't have installed.

---

## Solution

A Python MCP server (`wayback-mcp`) that gives Claude and other MCP-compatible hosts structured, rate-limit-safe access to the Internet Archive. Users can search by topic across all media types, retrieve and read archived web pages, explore a domain's archival history, and fetch rich structured metadata for any IA item — all without leaving their AI assistant. Deployable as `uvx wayback-mcp` with zero configuration.

---

## User Stories

1. As a researcher, I want to search the Internet Archive by topic in natural language, so that I can discover texts, audio, and video relevant to my subject without knowing specific identifiers.
2. As a journalist, I want to search for archived items from a specific time period, so that I can find primary sources from when an event occurred.
3. As a researcher, I want to filter archive searches by media type, so that I can find only books and texts rather than audio or video.
4. As a developer, I want to check whether a URL has ever been archived, so that I can determine if a dead link has a recoverable backup.
5. As a developer, I want to find the closest archived snapshot to a specific date, so that I can retrieve how a page looked at a particular point in time.
6. As a researcher, I want to read the text content of an archived web page, so that I can analyze its contents without opening a browser.
7. As a researcher, I want to know when a snapshot was actually captured (not just what I requested), so that I can correctly attribute the source date.
8. As a researcher, I want to know what media type a snapshot contains before extracting it, so that I am not surprised when a PDF cannot be read as text.
9. As a researcher, I want to get a direct link to a non-extractable archived file (PDF, image), so that I can open it myself even when the server cannot extract its text.
10. As a developer, I want to find all archived pages under a domain, so that I can understand what was captured from a site.
11. As a developer, I want to filter domain-wide archive searches by date range and HTTP status, so that I can find only successfully archived pages from a relevant period.
12. As a researcher, I want to retrieve rich structured metadata for any Internet Archive item, so that I can understand its provenance, creator, subject, and file formats.
13. As a developer, I want to get a list of all snapshots for a specific URL filtered by date and status code, so that I can programmatically navigate a URL's archival history.
14. As a researcher, I want to use reusable prompt workflows (research topic, track site changes, audit link rot), so that I can run complex multi-tool archive tasks without writing detailed instructions.
15. As a developer, I want the MCP server to run via `uvx wayback-mcp` with no installation, so that I can add it to Claude Desktop with one config block.
16. As a developer, I want the server to respect Internet Archive rate limits automatically, so that my IP is never blocked due to excessive requests.
17. As a developer, I want tool failures (snapshot not found, unsupported format, rate limit) to return structured error messages, so that Claude can explain what went wrong and suggest next steps.
18. As a developer, I want to access any Internet Archive item's metadata as an MCP resource at `wayback://item/{id}`, so that Claude can pull it into context without an explicit tool call.
19. As a team, I want the server to be extensible so that new tools (e.g. `save_url`) can be added in v2 without refactoring the transport, rate limiter, or existing tools.
20. As a future operator, I want the server architecture to support HTTP/SSE transport and API key auth middleware in v2, so that it can be deployed as a hosted service without rewriting tool logic.

---

## Implementation Decisions

### Modules

| Module | Responsibility |
|---|---|
| `src/server.py` | MCP entry point; registers all tools, prompts, resources; no business logic |
| `src/config.py` | All tuneable values: rate limits, endpoint URLs, User-Agent, result caps, timeouts |
| `src/models.py` | All Pydantic input/output models, centralized; shared models (e.g. `Snapshot`) defined once |
| `src/tools/search.py` | `search_archive`, `search_domain` |
| `src/tools/snapshots.py` | `lookup_snapshots`, `check_availability` |
| `src/tools/content.py` | `get_snapshot_content`, `get_item_metadata` |
| `src/client/http.py` | `httpx.AsyncClient` wrapper; injects User-Agent; handles retry on 5xx |
| `src/client/rate_limiter.py` | Async token-bucket per named endpoint key; 429 back-off honouring `Retry-After` |
| `src/client/parsers.py` | Raw IA API responses → typed Pydantic models; all parsing logic lives here |

### Architecture

- **Async throughout.** All tool handlers are `async def`. HTTP client is `httpx.AsyncClient`. Rate limiter uses `asyncio` primitives. Tests use `pytest-asyncio`.
- **Single rate limiter.** Dict of named async token buckets: `{"cdx": ..., "search": ..., "metadata": ...}`. All CDX-family tools share the `"cdx"` key. `search_archive` uses `"search"` (self-imposed ~30 rpm ceiling). No global rate budget is double-counted.
- **Transport-agnostic tools.** `server.py` calls `mcp.run(transport="stdio")` in v1. Switching to HTTP/SSE in v2 is a one-line change; no tool code is affected.
- **Error model.** Expected failures (snapshot not found, unsupported MIME type, item not found, rate limited) return a structured `ToolError` with a user-readable message. Unexpected failures raise exceptions and surface as MCP protocol errors.

### Tool decisions

**`search_archive`**
- Query string passed through to `advancedsearch.php` as-is — no Lucene validation.
- `mediatype` parameter is folded into the `q=` Lucene string, not passed as a separate URL param (separate param does not work reliably).
- Year range folded into `q=` as `AND year:[YYYY TO YYYY]`.
- Response path: `.response.numFound` and `.response.docs[]`.
- Fields `year`, `creator`, `subject`, `downloads` may be missing or null — all optional in model.

**`search_domain`**
- Auto-detects CDX `matchType`: input containing `/` after hostname → `matchType=prefix`; bare domain → `matchType=domain`.
- Must use `collapse=urlkey` to deduplicate heavily-crawled domains; without it, results are per-snapshot not per-URL.
- CDX row 0 is always the field header — data starts at `raw[1:]`.
- `JSONDecodeError` on empty date range → catch, return empty list.

**`get_item_metadata`**
- `subject` and `creator` fields can be `str` or `list[str]` — normalize to `list` in parser.
- Non-existent item returns `{}` or `{"error": "..."}` — guard both cases.
- `.files[].size` is a string, not int — cast carefully.
- `.item` aggregate stats block may be empty `{}` on sparse items.

**`get_snapshot_content`**
- Always calls `check_availability` first to resolve nearest snapshot URL and actual timestamp. Returns early with structured error if `available: false`.
- Uses the `if_` modifier in the fetch URL (`/web/{timestamp}if_/{url}`) to avoid the Wayback toolbar injection.
- MIME type gate (from CDX pre-check, not HTTP headers):
  - `text/html` → BeautifulSoup extraction
  - `text/plain` → raw text, capped at 10,000 characters
  - `application/pdf`, images, video, other → decline; return `snapshot_url` + message
- HTML extraction: try `<main>`, `<article>`, `role="main"` — if result > 200 words, use it; otherwise fall back to stripped body (`<script>` and `<style>` removed, Wayback toolbar stripped).
- Parser: `html.parser` (built-in; tolerant of malformed HTML from old archived pages).
- Response always includes: `content_type`, `extraction_method`, `word_count`, `snapshot_url`, `timestamp`, `truncated`.
- Truncate content at ~8,000 words to protect Claude's context window.

**`lookup_snapshots`**
- CDX row 0 is the field header — skip it, data from `raw[1:]`.
- All field values are strings — `statuscode` is `"200"` not `200`.
- `JSONDecodeError` on empty date range → catch, return `[]`.
- `len(raw) <= 1` means no snapshots found.
- `Snapshot` model exposes `.wayback_url` and `.content_url` as computed properties.

**`check_availability`**
- `.archived_snapshots` is `{}` (empty dict) when nothing is found — never access `.closest` directly.
- Always guard: `data.get("archived_snapshots", {}).get("closest")`.
- `"status"` in the response is the HTTP status of the archived page, not of the availability API call itself.

### Pydantic models (centralized in `src/models.py`)

Key shapes derived from verified API responses:

```python
class Snapshot(BaseModel):
    timestamp: str
    original_url: str
    status_code: str
    mimetype: str
    digest: Optional[str] = None

class SearchResult(BaseModel):
    identifier: str
    title: str
    mediatype: str
    year: Optional[Union[int, str]] = None
    creator: Optional[Union[str, List[str]]] = None
    subject: Optional[Union[str, List[str]]] = None
    downloads: Optional[int] = None

class AvailabilityResult(BaseModel):
    original_url: str
    available: bool
    snapshot_url: Optional[str] = None
    timestamp: Optional[str] = None
    status: Optional[str] = None

class ItemMetadata(BaseModel):
    identifier: str
    title: Optional[str] = None
    creator: Optional[Union[str, List[str]]] = None
    subject: Optional[Union[str, List[str]]] = None
    year: Optional[str] = None
    mediatype: Optional[str] = None
    description: Optional[Union[str, List[str]]] = None
    downloads: Optional[int] = None
    file_count: int = 0
```

### MCP surface area

**Tools (6):** `search_archive`, `search_domain`, `get_item_metadata`, `get_snapshot_content`, `lookup_snapshots`, `check_availability`

**Prompts (3):**
- `research_topic` — `search_archive` across mediatypes → `get_item_metadata` on top results → synthesise
- `track_site_changes` — `lookup_snapshots` → sample snapshots → `get_snapshot_content` × N → narrate
- `audit_link_rot` — iterates `check_availability` per URL (no `bulk_check_links`; dropped from v1)

**Resources (1):** `wayback://item/{id}` — full metadata of any IA item as JSON

### Packaging

- Published as `wayback-mcp` on PyPI
- Primary invocation: `uvx wayback-mcp` (zero-install)
- Entry point: `wayback_mcp.server:main`
- Runtime deps: `mcp>=1.0`, `httpx>=0.27`, `beautifulsoup4>=4.12`, `pydantic>=2.0`
- Python `>=3.11`

---

## Testing Decisions

**What makes a good test:** Tests assert on the structured output a tool returns (or the error it raises) given a specific mocked API response. They do not assert on which internal methods were called or how many HTTP requests were made. A test should fail only when observable behavior changes.

**Two-tier test suite:**

- **Unit tests (default):** Mock all HTTP with `respx`. Cover happy path, empty results, malformed/missing fields, and expected error cases for each tool. Fast, no network, always run in CI.
- **Integration tests (`@pytest.mark.integration`):** Hit real IA endpoints. Skipped by default; run with `pytest --integration`. Validate that real API response shapes match the Pydantic models. ~5–8 curated tests (one per tool). Run manually before releases.

**Modules with unit tests:** All 6 tool handlers, `parsers.py` (CDX array parsing, metadata field normalization), `rate_limiter.py` (token bucket behavior, 429 back-off), `http.py` (User-Agent injection, retry logic).

**Test fixtures:** Real API response shapes are captured in `agent-response.txt` and `wayback-test.sh` in the repo root. These are the authoritative reference for what `respx` mocks should return.

---

## Out of Scope (v1)

- `save_url` (Save Page Now) — deferred due to 24-hour IP block risk at 15 req/min hard limit
- HTTP/SSE transport — stdio covers all current MCP clients; transport switch is one line when needed
- Internet Archive S3 authenticated APIs — no upload/write use case in v1
- Full-text search (FTS beta) — unstable, undocumented endpoint
- PDF and document content extraction — most IA PDFs are scanned; adding `pypdf` deferred to v2
- `diff_snapshots` — web page diffs are not meaningful at the text level for archived content
- `bulk_check_links` — redundant with Claude iterating `check_availability`; dropped
- `wayback://snapshot/{url}` and `wayback://timeline/{url}` resources — URL-in-URI encoding footgun; covered by existing tools
- Per-user rate limiting — only relevant for hosted HTTP deployment (v2)
- Redis caching layer — deferred to v2
- MCP resource subscriptions — deferred to v2

---

## Further Notes

- **API response shapes are verified.** `agent-response.txt` and `wayback-test.sh` contain real, unmodified responses from all 6 target endpoints including edge cases (empty results, sparse items, non-existent identifiers, JSONDecodeError scenarios). Pydantic models in this PRD are derived from these verified shapes, not from documentation alone.
- **Post-2024 IA context.** Following the October 2024 security breach and ongoing legal proceedings, IA has tightened CDX rate limit enforcement. Conservative defaults in `config.py` and mandatory back-off are more important now than pre-2024.
- **User-Agent is mandatory.** IA's developer policy requires a descriptive User-Agent for all automated requests. Format: `WaybackMCP/1.0 Python/3.x (contact@email.com)`. Must be injected at the `http.py` layer so it cannot be accidentally omitted by individual tools.
- **CDX gotcha.** `row[0]` is always the field name header. Every CDX parser must skip it. `JSONDecodeError` on empty date ranges is expected behavior, not a bug — catch and return `[]`.
- **`check_availability` gotcha.** `.archived_snapshots` is an empty dict `{}` (not `null`, not missing) when a URL has no archive. Accessing `.closest` directly without `.get()` raises a `KeyError` on unarchived URLs.
