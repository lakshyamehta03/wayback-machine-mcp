# wayback-mcp

Python MCP server giving Claude structured access to the Internet Archive's Wayback Machine.

## Documentation

- `research/PRD.md` — Full product requirements, implementation decisions, and testing plan; primary reference for implementation
- `research/design-decisions.md` — Finalized decisions from design review; supersedes open questions in the research doc
- `research/wayback-mcp-research.md` — API feasibility study, prior art, original architecture and MCP surface area design
- `agent-response.txt` — Verified live API response shapes for all 6 endpoints, including edge cases; authoritative reference for parsers and test mocks

## Project structure

```
src/                           # Python source — maps to wayback_mcp package
  server.py          # MCP entry point, tool/prompt/resource registration
  config.py          # Rate limits, timeouts, endpoint URLs, User-Agent, result caps
  models.py          # All Pydantic input/output models (centralized)
  tools/
    search.py        # search_archive, search_domain
    snapshots.py     # lookup_snapshots, check_availability
    content.py       # get_snapshot_content, get_item_metadata
  client/
    http.py          # httpx.AsyncClient, User-Agent injection, retry logic
    rate_limiter.py  # Async token-bucket per named endpoint key, 429 back-off
    parsers.py       # Raw API responses → typed Pydantic models
tests/
  test_search.py
  test_snapshots.py
  test_content.py
  test_client.py
  integration/       # Real IA API calls — run with pytest --integration
```

## Commands

```bash
uv run wayback-mcp             # run server (stdio)
uv run pytest                  # unit tests (mocked via respx)
uv run pytest --integration    # unit + integration tests (hits live IA APIs)
```

## Constraints

- All outbound requests must pass through `client/rate_limiter.py` — never call IA APIs directly from tool files
- All tuneable values (rate limits, result caps, endpoint URLs, User-Agent) live in `config.py`
- Tool handlers are `async def` throughout; use `httpx.AsyncClient`
- Expected failures (snapshot not found, unsupported MIME type, rate limited) return structured errors via `ToolError`; unexpected failures raise exceptions
- Pydantic models are defined in `src/models.py` (installed as `wayback_mcp.models`), not inline in tool files

## Agent skills

### Issue tracker

Issues live in GitHub Issues for this repo, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Using canonical defaults: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/` at the repo root). See `docs/agents/domain.md`.
