<div align="center">

<img src="https://raw.githubusercontent.com/lakshyamehta03/wayback-machine-mcp/main/Wayback_Machine_logo_2010.svg" alt="Wayback Machine" width="420" />

# wayback-mcp

**A Model Context Protocol server giving Claude and other LLM clients structured access to the Internet Archive's Wayback Machine.**

[![PyPI](https://img.shields.io/pypi/v/mcp-server-wayback.svg)](https://pypi.org/project/mcp-server-wayback/)
[![CI](https://github.com/lakshyamehta03/wayback-machine-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/lakshyamehta03/wayback-machine-mcp/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0+-8A2BE2.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<br/>

<img src="https://raw.githubusercontent.com/lakshyamehta03/wayback-machine-mcp/main/demo.gif" alt="wayback-mcp demo" width="700" />

</div>

---

## Overview

`wayback-mcp` is an async Python MCP server that exposes the Internet Archive's six core APIs — Availability, CDX, Advanced Search, Metadata, and Wayback content — as first-class tools, prompts, and resources for any MCP-compatible client. It handles rate limiting, retry/back-off, and response shape normalisation so the model only sees structured Pydantic data.

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

### As an MCP server

#### Interactive installer (recommended)

```bash
uvx mcp-server-wayback --install
```

You'll get a numbered menu of supported clients — pick one, the installer writes the config for you, then restart that client. Run `uvx mcp-server-wayback --list-clients` to see the menu without launching it.

#### Non-interactive installers

Pass the client key explicitly (handy for scripts and dotfiles):

```bash
uvx mcp-server-wayback --install claude-desktop
uvx mcp-server-wayback --install claude-code-user        # ~/.claude.json
uvx mcp-server-wayback --install claude-code-project     # ./.mcp.json in cwd
uvx mcp-server-wayback --install cursor                  # ./.cursor/mcp.json
uvx mcp-server-wayback --install windsurf
uvx mcp-server-wayback --install zed                     # uses Zed's context_servers key
uvx mcp-server-wayback --install antigravity             # ~/.gemini/antigravity/mcp_config.json
```

For clients with their own MCP CLI:

```bash
claude mcp add wayback -- uvx mcp-server-wayback
codex mcp add wayback -- uvx mcp-server-wayback
```

To include Internet Archive API keys for higher rate limits at install time:

```bash
claude mcp add wayback \
  --env WAYBACK_MCP_IA_ACCESS_KEY=xxx \
  --env WAYBACK_MCP_IA_SECRET_KEY=xxx \
  -- uvx mcp-server-wayback
```

> Need [`uvx`](https://docs.astral.sh/uv/getting-started/installation/)? `brew install uv` on macOS, or `pipx install uv`. Python 3.11+ required.

#### Manual configuration

For clients that use a JSON config file, add this to the appropriate section:

```json
{
  "wayback": {
    "command": "uvx",
    "args": ["mcp-server-wayback"],
    "env": {
      "WAYBACK_MCP_IA_ACCESS_KEY": "your-access-key",
      "WAYBACK_MCP_IA_SECRET_KEY": "your-secret-key"
    }
  }
}
```

The `env` block is optional — the server works anonymously without credentials. See [Authentication](#authentication) for details.

| Client | Config file | Config key |
|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) | `mcpServers` |
| Claude Code | `.mcp.json` (project) / `~/.claude.json` (user) | `mcpServers` |
| Google Antigravity | `~/.gemini/antigravity/mcp_config.json` | `mcpServers` |
| Codex CLI | `~/.codex/config.toml` | `[mcp_servers.wayback]` |
| Cursor | `.cursor/mcp.json` | `mcpServers` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` |
| Cline | `.cline/mcp.json` | `mcpServers` |
| Zed | `~/.config/zed/settings.json` | `context_servers` |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` |

#### Project-scoped (workspace) config

Claude Code supports a per-workspace `.mcp.json` in the repo root. Useful for testing env-var changes without touching your global config:

```bash
claude mcp add wayback --scope project -- uvx mcp-server-wayback
```

Open Claude Code from that folder — it picks up `.mcp.json` automatically. Add it to `.gitignore` if it contains real keys.

#### Uninstalling

```bash
uvx mcp-server-wayback --uninstall                  # interactive picker
uvx mcp-server-wayback --uninstall claude-desktop   # or pass a client key
claude mcp remove wayback                           # Claude Code native CLI
codex mcp remove wayback                            # Codex CLI native CLI
```

## Quick examples

What to ask the agent once the server is wired up:

```
Has openai.com been archived? Show me the closest snapshot.
```

```
Find archived snapshots of nytimes.com from 2001.
```

```
What did anthropic.com look like in early 2023?
```

```
Search the Internet Archive for documentaries about the moon landing.
```

```
Walk me through how anthropic.com's homepage has changed over the past year.
```

```
I have a list of URLs from a 2015 reading list — check which are still recoverable from the Wayback Machine.
```

Or use a slash command for a guided workflow: `/wayback:research_topic`, `/wayback:track_site_changes`, `/wayback:audit_link_rot`, `/wayback:setup_authentication`.

## Tools

### `check_availability`

Check whether a URL has been archived and return the closest snapshot.

<details>
<summary>Parameters</summary>

| Parameter | Required | Description |
|---|---|---|
| `url` | Yes | The URL to check |
| `timestamp` | No | Target timestamp (`YYYYMMDDhhmmss`). Returns the snapshot closest to this point in time. Omit for the most recent. |

</details>

### `lookup_snapshots`

List all CDX snapshots for a URL with optional date-range and HTTP-status filters.

<details>
<summary>Parameters</summary>

| Parameter | Required | Description |
|---|---|---|
| `url` | Yes | The URL to look up |
| `from_date` | No | Start of range (`YYYYMMDD`) |
| `to_date` | No | End of range (`YYYYMMDD`) |
| `status_code` | No | Filter by HTTP status, e.g. `"200"` to drop redirects and errors |
| `limit` | No | Maximum results (defaults to `CDX_MAX_RESULTS` = 50) |

</details>

### `search_archive`

Search Internet Archive collections using Lucene query syntax. Returns matching items with identifier, title, mediatype, year, creator, subject, and download count.

<details>
<summary>Parameters</summary>

| Parameter | Required | Description |
|---|---|---|
| `query` | Yes | Lucene query, e.g. `"apollo 11"` or `creator:"NASA"` |
| `mediatype` | No | Filter by type: `"texts"`, `"audio"`, `"movies"`, `"image"`, `"software"`, `"web"` |
| `year_from` | No | Earliest publication year |
| `year_to` | No | Latest publication year |
| `limit` | No | Maximum results (defaults to `SEARCH_MAX_RESULTS` = 50) |

</details>

### `search_domain`

Discover archived URLs under a domain or path prefix. Auto-detects whether to do a wildcard-domain or prefix match from the input shape.

<details>
<summary>Parameters</summary>

| Parameter | Required | Description |
|---|---|---|
| `domain` | Yes | Bare domain (`example.com`) for subdomain wildcard, or `example.com/blog` for path prefix |
| `from_date` | No | Start of range (`YYYYMMDD`) |
| `to_date` | No | End of range (`YYYYMMDD`) |
| `status_code` | No | Filter by HTTP status |
| `limit` | No | Maximum results |

</details>

### `get_snapshot_content`

Fetch an archived web page and extract its readable text. Strips the Wayback toolbar, navigation, and boilerplate so the model only sees article-quality content.

<details>
<summary>Parameters</summary>

| Parameter | Required | Description |
|---|---|---|
| `url` | Yes | The URL to fetch the archived content of |
| `timestamp` | No | Target snapshot timestamp (`YYYYMMDDhhmmss`). Omit for the latest. |

Returns `{text, word_count, snapshot_url, timestamp, sparse_content_warning}`.

</details>

### `get_item_metadata`

Return rich structured metadata for any Internet Archive item by its identifier.

<details>
<summary>Parameters</summary>

| Parameter | Required | Description |
|---|---|---|
| `identifier` | Yes | The IA item identifier, e.g. `"nasa_Apollo_11"` |

Returns title, description, creator, subject, mediatype, year, downloads, full file list, and more.

</details>

## Prompts

| Prompt | What it does |
|---|---|
| `research_topic` | Multi-mediatype IA search → synthesised topic overview |
| `track_site_changes` | Sample snapshots over time → narrate how a page evolved |
| `audit_link_rot` | Bulk-check URLs and surface archived alternatives |
| `setup_authentication` | Walks the user through configuring IA S3 keys |

## Resources

| URI template | Returns |
|---|---|
| `wayback://item/{identifier}` | Full Internet Archive item metadata as JSON |

## Authentication

The server works anonymously by default. Configure Internet Archive S3 keys to raise your rate-limit ceiling and remove `429` errors during heavy use:

1. Visit <https://archive.org/account/s3.php> (free archive.org account required)
2. Copy your access key and secret key
3. Add them to the `env` block of your MCP config (see [Manual configuration](#manual-configuration)) — or run the `setup_authentication` prompt for an interactive walkthrough

Keys never leave your machine. They live only in your local MCP config and the server subprocess's environment.

## Technical details

- **Transport**: stdio (MCP client integration)
- **Caching**: in-memory with per-endpoint TTLs
  - Metadata, snapshot content: 24 hours (immutable once captured)
  - CDX results: 1 hour (grows but never mutates)
  - Search results: 15 minutes (relevance can shift)
- **Rate limiting**: async token-bucket per endpoint group with automatic `Retry-After` handling for `429` responses
- **Validation**: Pydantic 2 schemas for every input and output
- **Python 3.11+**

## Development

```bash
git clone https://github.com/lakshyamehta03/wayback-machine-mcp.git
cd wayback-machine-mcp
uv sync
uv run mcp-server-wayback      # run the server
uv run pytest                  # unit tests (httpx mocked via respx)
uv run pytest --integration    # also hit live Internet Archive APIs
```

CI runs the unit suite on every push and pull request via GitHub Actions.

## License

[MIT](LICENSE). The Wayback Machine logo is © Internet Archive and used here under fair use to identify the upstream service this project integrates with.

## Acknowledgments

- The [Internet Archive](https://archive.org/) for the Wayback Machine and the open APIs that make this server possible
- [Anthropic](https://www.anthropic.com/) for the [Model Context Protocol](https://modelcontextprotocol.io/) specification and SDK
