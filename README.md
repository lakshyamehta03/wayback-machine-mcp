<div align="center">

<img src="Wayback_Machine_logo_2010.svg" alt="Wayback Machine" width="420" />

# wayback-mcp

**A Model Context Protocol server giving Claude structured access to the Internet Archive's Wayback Machine.**

[![CI](https://github.com/lakshyamehta03/wayback-machine-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/lakshyamehta03/wayback-machine-mcp/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0+-8A2BE2.svg)](https://modelcontextprotocol.io/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-DE5FE9.svg)](https://github.com/astral-sh/uv)

</div>

---

## Overview

`wayback-mcp` is an async Python MCP server that exposes the Internet Archive's six core APIs — Availability, CDX, Advanced Search, Metadata, and Wayback content — as first-class tools, prompts, and resources for Claude. It handles rate limiting, retry/back-off, and response shape normalisation so the model only sees structured Pydantic data.

## Features

- **Six MCP tools** covering availability checks, snapshot lookups, full-text item search, domain crawls, page-text extraction, and item metadata
- **Four guided prompts** — `research_topic`, `track_site_changes`, `audit_link_rot`, `setup_authentication`
- **One MCP resource** — `wayback://item/{identifier}` exposes IA item metadata as JSON
- **Async token-bucket rate limiter** with per-endpoint buckets and `Retry-After` honoring
- **In-memory response cache** with per-endpoint TTLs to keep token usage and IA load low
- **Internet Archive S3 authentication** (optional) for higher rate-limit ceilings
- **Structured error model** — expected failures return `ToolError`; unexpected ones raise
- **Tested against live IA APIs** via an opt-in `--integration` pytest flag

## Installation

Requires Python 3.11+ and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/lakshyamehta03/wayback-machine-mcp.git
cd wayback-machine-mcp
uv sync
```

## Usage

### Run the server

```bash
uv run wayback-mcp
```

The server speaks MCP over stdio.

### Wire it into Claude Desktop

Add an entry to `claude_desktop_config.json` (on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "wayback": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/wayback-machine-mcp", "run", "wayback-mcp"]
    }
  }
}
```

Restart Claude Desktop. The `wayback` tools, prompts, and resources will appear in the MCP picker.

### Optional: Internet Archive authentication

Set both keys in the server's environment to authenticate every IA request and raise your rate-limit ceiling. Run the `setup_authentication` prompt from Claude to walk through it interactively.

```json
"env": {
  "WAYBACK_MCP_IA_ACCESS_KEY": "<your access key>",
  "WAYBACK_MCP_IA_SECRET_KEY": "<your secret key>"
}
```

Get keys at <https://archive.org/account/s3.php>.

## Tools

| Tool | Purpose |
|---|---|
| `check_availability` | Is this URL archived? Returns the closest snapshot |
| `lookup_snapshots` | List CDX snapshots for a URL with date / status filters |
| `search_archive` | Lucene search across IA collections with mediatype + year range |
| `search_domain` | Discover archived URLs under a domain or path prefix |
| `get_snapshot_content` | Fetch an archived page and extract its readable text |
| `get_item_metadata` | Rich structured metadata for any IA item identifier |

## Prompts

| Prompt | What it does |
|---|---|
| `research_topic` | Multi-mediatype IA search → synthesised topic overview |
| `track_site_changes` | Sample snapshots over time → narrate how a page evolved |
| `audit_link_rot` | Bulk-check URLs and surface archived alternatives |
| `setup_authentication` | Walks the user through configuring IA S3 keys |

## Project structure

```
src/                  # wayback_mcp package
  server.py           # MCP entry point — tools, prompts, resources
  config.py           # Rate limits, timeouts, endpoint URLs, caps
  models.py           # All Pydantic input/output models
  tools/              # search, snapshots, content
  client/             # http, rate_limiter, parsers
tests/
  integration/        # Real IA API calls — opt-in via --integration
research/             # PRD, design decisions, API research
docs/adr/             # Architecture decision records
CONTEXT.md            # Domain glossary, invariants, implementation notes
```

## Development

### Running tests

```bash
uv run pytest                  # unit tests (httpx mocked via respx)
uv run pytest --integration    # also hit live Internet Archive APIs
```

CI runs the unit suite on every push and pull request via GitHub Actions.

### Architectural invariants

These are enforced — see [`CONTEXT.md`](CONTEXT.md) for the full list:

- All IA requests route through `client/http.py` → `client/rate_limiter.py`. Tool files never call IA directly.
- All tuneable values (rate limits, result caps, endpoint URLs, User-Agent) live in `config.py`.
- Pydantic models live in `src/models.py`, never inline in tool files.
- Expected failures return `ToolError`; unexpected failures raise.

## Documentation

- [`CONTEXT.md`](CONTEXT.md) — domain glossary, invariants, verified live-API quirks
- [`research/PRD.md`](research/PRD.md) — full product requirements
- [`research/design-decisions.md`](research/design-decisions.md) — finalised design review outcomes
- [`research/wayback-mcp-research.md`](research/wayback-mcp-research.md) — API feasibility study and prior art
- [`docs/adr/`](docs/adr/) — architecture decision records

## License

No license file is currently included in this repository. The Wayback Machine logo is © Internet Archive and used here under fair use to identify the upstream service this project integrates with.

## Acknowledgments

- The [Internet Archive](https://archive.org/) for the Wayback Machine and the open APIs that make this server possible
- [Anthropic](https://www.anthropic.com/) for the [Model Context Protocol](https://modelcontextprotocol.io/) specification and SDK
