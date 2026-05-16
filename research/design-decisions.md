# Wayback MCP — Design Decisions

Finalized during design review. Supersedes open questions in `wayback-mcp-research.md`.

---

## Tool surface area (v1)

6 tools (down from 8 in original design):

| Tool | Module |
|---|---|
| `search_archive` | `tools/search.py` |
| `search_domain` | `tools/search.py` |
| `get_item_metadata` | `tools/content.py` |
| `get_snapshot_content` | `tools/content.py` |
| `lookup_snapshots` | `tools/snapshots.py` |
| `check_availability` | `tools/snapshots.py` |

**Dropped from original design:**
- `diff_snapshots` — archived web pages don't diff meaningfully; return snapshot URLs and let user compare visually
- `bulk_check_links` — redundant with Claude calling `check_availability` in a loop; MCP handles iteration naturally

**MCP resources:** `wayback://item/{id}` only. `wayback://snapshot/{url}` and `wayback://timeline/{url}` dropped — URL-in-URI path creates encoding footguns, and functionality is covered by existing tools.

**Prompts:** 3 retained (`research_topic`, `track_site_changes`, `audit_link_rot`). `audit_link_rot` must be updated to orchestrate `check_availability` calls directly instead of the dropped `bulk_check_links`.

---

## Architectural decisions

### Async
All tool handlers are `async def`. Use `httpx.AsyncClient`. Rate limiter uses `asyncio.Semaphore` or async token bucket. Tests require `pytest-asyncio`.

### Rate limiter
Single dict of named async token buckets: `{"cdx": TokenBucket, "search": TokenBucket, "metadata": TokenBucket}`. All CDX-family calls (`lookup_snapshots`, `check_availability`, `search_domain`) share the `"cdx"` key. `search_archive` uses `"search"` (conservative self-imposed ceiling ~30 rpm). No explicit group abstraction.

### Pydantic models
Centralized in `src/models.py`. All tool input and output models live here. Tool files and `parsers.py` import from `models.py`. Avoids duplication of shared shapes (e.g. `SnapshotRecord` used across multiple tools).

### Error handling
- Expected failures (snapshot not found, unsupported MIME type, 429, IA 404): return structured `ToolError` with message
- Unexpected failures (network errors, parsing bugs): raise exceptions, let MCP SDK convert to protocol error
- Every tool response carries `error: str | None`; on failure, other fields are null

### Testing
Two-tier:
- Unit tests (default): `respx` mocks for all HTTP; fast, no network
- Integration tests: `@pytest.mark.integration`, skipped by default, run with `pytest --integration`; hit real IA endpoints to validate response shapes; ~5 curated tests

---

## Per-tool decisions

### `get_snapshot_content`
1. Always call `check_availability` first to resolve the nearest snapshot URL and actual timestamp
2. If `available: false`, return early with structured error — no fetch needed
3. HTML extraction: try `<main>`, `<article>`, `role="main"` first; if none found or result < 200 words, fall back to full body after stripping Wayback toolbar + `<script>` + `<style>`
4. Non-HTML MIME types (PDF, images, video, etc.): return `{content: null, extractable: false, reason: "...", snapshot_url: "..."}` — no extraction, no extra deps in v1
5. Parser: `html.parser` (built-in, handles malformed HTML from old archived pages)

### `search_archive`
- Query string passed through to `advancedsearch.php` as-is — no Lucene validation or preprocessing
- Trust Claude to form valid queries; document Lucene syntax support in tool description
- 0 results on malformed query is acceptable failure mode

### `search_domain`
- Auto-detect CDX `matchType` from input: if `domain` contains `/` after hostname → `matchType=prefix`; bare domain → `matchType=domain`
- No explicit `match_type` input parameter

### `diff_snapshots`
- Dropped. See tool surface area above.

### `bulk_check_links`
- Dropped. See tool surface area above.
