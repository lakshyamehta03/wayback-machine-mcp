"""One-shot installer that wires this server into a chosen MCP client's config.

Invoked via the `--install` / `--uninstall` flags on the package's console
script. With no client argument, presents an interactive picker (like a skill
installer). With a client argument, runs non-interactively for scripting.

Supported clients:

- claude-desktop          Claude Desktop (global)
- claude-code-user        Claude Code (user-scope: ~/.claude.json)
- claude-code-project     Claude Code (project-scope: ./.mcp.json)
- cursor                  Cursor (project-scope: ./.cursor/mcp.json)
- windsurf                Windsurf (global)
- zed                     Zed (global; uses `context_servers` key)
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

IA_KEYS_URL = "https://archive.org/account/s3.php"
ACCESS_KEY_ENV = "WAYBACK_MCP_IA_ACCESS_KEY"
SECRET_KEY_ENV = "WAYBACK_MCP_IA_SECRET_KEY"

SERVER_KEY = "wayback"
SERVER_ENTRY = {
    "command": "uvx",
    "args": ["mcp-server-wayback"],
}


# ---------------------------------------------------------------------------
# Client registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Client:
    """Static description of an MCP-compatible client we know how to install into."""

    key: str
    label: str
    config_path: Callable[[], Path]
    container_key: str = "mcpServers"


def _claude_desktop_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _claude_code_user_path() -> Path:
    return Path.home() / ".claude.json"


def _claude_code_project_path() -> Path:
    return Path.cwd() / ".mcp.json"


def _cursor_project_path() -> Path:
    return Path.cwd() / ".cursor" / "mcp.json"


def _windsurf_path() -> Path:
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


def _zed_path() -> Path:
    return Path.home() / ".config" / "zed" / "settings.json"


CLIENTS: tuple[Client, ...] = (
    Client("claude-desktop", "Claude Desktop", _claude_desktop_path),
    Client("claude-code-user", "Claude Code (user-scope, ~/.claude.json)", _claude_code_user_path),
    Client(
        "claude-code-project",
        "Claude Code (project-scope, ./.mcp.json in current directory)",
        _claude_code_project_path,
    ),
    Client("cursor", "Cursor (project-scope, ./.cursor/mcp.json)", _cursor_project_path),
    Client("windsurf", "Windsurf", _windsurf_path),
    Client("zed", "Zed", _zed_path, container_key="context_servers"),
)


def get_client(key: str) -> Client | None:
    """Look up a client record by its CLI key."""
    return next((c for c in CLIENTS if c.key == key), None)


def _client_keys_csv() -> str:
    return ", ".join(c.key for c in CLIENTS)


# Backwards compat: this used to be the only path the installer knew about.
# Keep the helper around because external callers (and earlier tests) imported it.
def claude_desktop_config_path() -> Path:
    return _claude_desktop_path()


# ---------------------------------------------------------------------------
# Interactive picker
# ---------------------------------------------------------------------------


def pick_client_interactively(
    stream_in=None,
    stream_out=None,
) -> Client | None:
    """Prompt the user to pick a client. Returns the choice, or None if cancelled.

    Streams default to sys.stdin / sys.stdout but are injectable for tests.
    """
    stream_in = stream_in or sys.stdin
    stream_out = stream_out or sys.stdout

    print("Which MCP client are you installing the wayback server into?\n", file=stream_out)
    for i, c in enumerate(CLIENTS, start=1):
        print(f"  {i}. {c.label}", file=stream_out)
    cancel_n = len(CLIENTS) + 1
    print(f"  {cancel_n}. Cancel\n", file=stream_out)

    while True:
        print(f"Pick [1-{cancel_n}]: ", end="", file=stream_out, flush=True)
        line = stream_in.readline()
        if not line:  # EOF (non-interactive stdin)
            print("(no choice provided)", file=stream_out)
            return None
        choice = line.strip()
        if not choice.isdigit():
            print("Please enter a number.", file=stream_out)
            continue
        n = int(choice)
        if n == cancel_n:
            return None
        if 1 <= n <= len(CLIENTS):
            return CLIENTS[n - 1]
        print(f"Pick a number between 1 and {cancel_n}.", file=stream_out)


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    return json.loads(text)


# Script name we ship as a console entry point. Used to identify wayback
# entries by their invocation, not by the user's chosen config-key name.
_SCRIPT_NAME = "mcp-server-wayback"


def _matches_server_entry(entry: object) -> bool:
    """True if `entry` looks like an invocation of this server.

    Matches:
      - direct: command == "mcp-server-wayback"
      - uvx: command == "uvx" and "mcp-server-wayback" in args
      - uv run: command == "uv" and "mcp-server-wayback" in args
        (covers `uv run mcp-server-wayback` from a local-dev checkout)

    Matches on the exact script name, never a substring, to avoid false
    positives like "my-mcp-server-wayback-fork".
    """
    if not isinstance(entry, dict):
        return False
    cmd = entry.get("command")
    if cmd == _SCRIPT_NAME:
        return True
    if cmd in ("uvx", "uv"):
        args = entry.get("args") or []
        if isinstance(args, list) and _SCRIPT_NAME in args:
            return True
    return False


def _find_server_entries(servers: dict) -> list[str]:
    """Return all keys in `servers` whose entry looks like our server,
    regardless of the user's chosen key name."""
    if not isinstance(servers, dict):
        return []
    return [k for k, v in servers.items() if _matches_server_entry(v)]


def _resolve_target_key(servers: dict, config_path: Path, client_key: str) -> str | None:
    """Pick the single key to mutate for set/clear-auth operations.

    Prefers the canonical `wayback` key when present; otherwise uses the sole
    matching entry. Returns None and prints a user-facing error if no entry is
    found or if multiple non-default matches are ambiguous.
    """
    if SERVER_KEY in servers:
        return SERVER_KEY
    matches = _find_server_entries(servers)
    if not matches:
        print(
            f"error: wayback isn't in {config_path}.\n"
            f"Run `mcp-server-wayback --install {client_key}` first.",
            file=sys.stderr,
        )
        return None
    if len(matches) == 1:
        return matches[0]
    print(
        f"error: multiple wayback server entries found in {config_path}: "
        f"{', '.join(matches)}.\n"
        f"Rename one to '{SERVER_KEY}' or remove the duplicates first.",
        file=sys.stderr,
    )
    return None


def install(
    client_key: str = "claude-desktop",
    *,
    path: Path | None = None,
    force: bool = False,
) -> int:
    """Add the wayback entry to the chosen client's config. Returns an exit code.

    `path` overrides the client's default config path (used by tests).
    """
    client = get_client(client_key)
    if client is None:
        print(
            f"error: unknown client '{client_key}'. Supported: {_client_keys_csv()}",
            file=sys.stderr,
        )
        return 2

    config_path = path or client.config_path()

    try:
        config = _load_config(config_path)
    except json.JSONDecodeError as e:
        print(
            f"error: {config_path} exists but isn't valid JSON ({e}).\n"
            "Fix the file or move it aside, then retry.",
            file=sys.stderr,
        )
        return 1

    servers = config.setdefault(client.container_key, {})
    if SERVER_KEY in servers and not force:
        print(f"wayback is already configured in {config_path}.")
        print("Re-run with --uninstall first if you want to reinstall.")
        return 0

    servers[SERVER_KEY] = SERVER_ENTRY
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    abs_path = config_path.resolve()
    entry = servers[SERVER_KEY]
    has_auth = bool(entry.get("env", {}).get(ACCESS_KEY_ENV) and entry.get("env", {}).get(SECRET_KEY_ENV))

    print(f"✓ Added wayback to {abs_path}")
    print(f"Restart {client.label} to load it.")
    if not has_auth:
        print()
        print("Optional but recommended: configure free Internet Archive API keys")
        print("to raise your rate-limit ceiling and avoid 429 errors.")
        print(f"  1. Get keys (free, 30s): {IA_KEYS_URL}")
        print(f"  2. Run: mcp-server-wayback --set-auth {client.key}")
        print("  3. Restart your client.")
    return 0


def uninstall(
    client_key: str = "claude-desktop",
    *,
    path: Path | None = None,
    force: bool = False,
    stream_in=None,
    stream_out=None,
) -> int:
    """Remove the wayback entry from the chosen client's config. Returns an exit code.

    Matches entries by their invocation (see `_matches_server_entry`), not just
    by the hardcoded `wayback` key — so a user who installed manually under a
    different key name (e.g. `wayback-mcp`) is still covered. When matches are
    found under non-default keys, prompts for confirmation before removing
    unless `force=True`.
    """
    client = get_client(client_key)
    if client is None:
        print(
            f"error: unknown client '{client_key}'. Supported: {_client_keys_csv()}",
            file=sys.stderr,
        )
        return 2

    config_path = path or client.config_path()

    if not config_path.exists():
        print(f"No config at {config_path} — nothing to remove.")
        return 0

    try:
        config = _load_config(config_path)
    except json.JSONDecodeError as e:
        print(f"error: {config_path} isn't valid JSON ({e}).", file=sys.stderr)
        return 1

    servers = config.get(client.container_key, {})
    matches = _find_server_entries(servers)
    # Also remove the canonical key if it exists but its entry shape doesn't
    # match (e.g. legacy/corrupt entry under "wayback") — preserves prior
    # behavior of always cleaning out the default key on uninstall.
    if SERVER_KEY in servers and SERVER_KEY not in matches:
        matches.append(SERVER_KEY)

    if not matches:
        print(f"wayback isn't in {config_path} — nothing to remove.")
        return 0

    non_default = [k for k in matches if k != SERVER_KEY]
    if non_default and not force:
        stream_in = stream_in or sys.stdin
        stream_out = stream_out or sys.stdout
        print(
            f"Found wayback server entries under non-default keys in {config_path}:",
            file=stream_out,
        )
        for k in non_default:
            print(f"  - {k}", file=stream_out)
        print("Remove these too? [y/N]: ", end="", file=stream_out, flush=True)
        answer = stream_in.readline().strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled. Re-run with --force to skip this prompt.", file=stream_out)
            # If the default key was also matched, still remove it — that's the
            # "old" --uninstall behavior the user explicitly invoked.
            if SERVER_KEY not in matches:
                return 0
            matches = [SERVER_KEY]

    for key in matches:
        servers.pop(key, None)
    if not servers:
        del config[client.container_key]
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    removed_desc = ", ".join(matches)
    print(f"✓ Removed wayback ({removed_desc}) from {config_path.resolve()}")
    print(f"Restart {client.label} for the change to take effect.")
    return 0


# ---------------------------------------------------------------------------
# Auth key setup — agent-agnostic, writes to whichever client's config the
# wayback entry already lives in.
# ---------------------------------------------------------------------------


def _read_text(prompt: str, stream_in, stream_out) -> str:
    print(prompt, end="", file=stream_out, flush=True)
    line = stream_in.readline()
    if not line:
        return ""
    return line.strip()


def set_auth(
    client_key: str = "claude-desktop",
    *,
    path: Path | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    stream_in=None,
    stream_out=None,
    read_secret: Callable[[str], str] | None = None,
) -> int:
    """Write IA S3 keys into the env block of the chosen client's wayback entry.

    Prompts interactively for any key not passed explicitly. Secret key reads
    via getpass so it doesn't echo. Preserves any other env vars already set.
    """
    stream_in = stream_in or sys.stdin
    stream_out = stream_out or sys.stdout
    read_secret = read_secret or getpass.getpass

    client = get_client(client_key)
    if client is None:
        print(
            f"error: unknown client '{client_key}'. Supported: {_client_keys_csv()}",
            file=sys.stderr,
        )
        return 2

    config_path = path or client.config_path()

    if not config_path.exists():
        print(
            f"error: no config at {config_path}.\n"
            f"Run `mcp-server-wayback --install {client.key}` first.",
            file=sys.stderr,
        )
        return 1

    try:
        config = _load_config(config_path)
    except json.JSONDecodeError as e:
        print(f"error: {config_path} isn't valid JSON ({e}).", file=sys.stderr)
        return 1

    servers = config.get(client.container_key, {})
    target_key = _resolve_target_key(servers, config_path, client.key)
    if target_key is None:
        return 1

    if access_key is None:
        print(f"Get free IA API keys at {IA_KEYS_URL}", file=stream_out)
        access_key = _read_text("Access key: ", stream_in, stream_out)
    access_key = access_key.strip()
    if not access_key:
        print("error: access key is required.", file=sys.stderr)
        return 1

    if secret_key is None:
        secret_key = read_secret("Secret key (hidden): ")
    secret_key = secret_key.strip()
    if not secret_key:
        print("error: secret key is required.", file=sys.stderr)
        return 1

    entry = servers[target_key]
    env = entry.setdefault("env", {})
    env[ACCESS_KEY_ENV] = access_key
    env[SECRET_KEY_ENV] = secret_key

    config_path.write_text(json.dumps(config, indent=2) + "\n")

    print(f"✓ Wrote IA auth keys to {config_path.resolve()}")
    print(f"Restart {client.label} to activate them.")
    return 0


def clear_auth(
    client_key: str = "claude-desktop",
    *,
    path: Path | None = None,
) -> int:
    """Remove IA S3 keys from the chosen client's wayback env block.

    Preserves any other env vars. Removes the env block entirely if it becomes
    empty.
    """
    client = get_client(client_key)
    if client is None:
        print(
            f"error: unknown client '{client_key}'. Supported: {_client_keys_csv()}",
            file=sys.stderr,
        )
        return 2

    config_path = path or client.config_path()

    if not config_path.exists():
        print(f"No config at {config_path} — nothing to clear.")
        return 0

    try:
        config = _load_config(config_path)
    except json.JSONDecodeError as e:
        print(f"error: {config_path} isn't valid JSON ({e}).", file=sys.stderr)
        return 1

    servers = config.get(client.container_key, {})
    matches = _find_server_entries(servers)
    if SERVER_KEY in servers and SERVER_KEY not in matches:
        matches.append(SERVER_KEY)
    if not matches:
        print(f"wayback isn't in {config_path} — nothing to clear.")
        return 0
    if SERVER_KEY in matches:
        target_key = SERVER_KEY
    elif len(matches) == 1:
        target_key = matches[0]
    else:
        print(
            f"error: multiple wayback server entries found in {config_path}: "
            f"{', '.join(matches)}.\n"
            f"Rename one to '{SERVER_KEY}' or remove the duplicates first.",
            file=sys.stderr,
        )
        return 1

    entry = servers[target_key]
    env = entry.get("env", {})
    removed = False
    for key in (ACCESS_KEY_ENV, SECRET_KEY_ENV):
        if key in env:
            del env[key]
            removed = True
    if "env" in entry and not entry["env"]:
        del entry["env"]

    if not removed:
        print(f"No IA auth keys found in {config_path} — nothing to clear.")
        return 0

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"✓ Cleared IA auth keys from {config_path.resolve()}")
    print(f"Restart {client.label} for the change to take effect.")
    return 0


# ---------------------------------------------------------------------------
# Auth setup guide (shared with prompts and 429 errors — single source of truth)
# ---------------------------------------------------------------------------


AUTH_CONFIG_SNIPPET = """```json
{
  "mcpServers": {
    "wayback": {
      "command": "uvx",
      "args": ["mcp-server-wayback"],
      "env": {
        "WAYBACK_MCP_IA_ACCESS_KEY": "<paste access key>",
        "WAYBACK_MCP_IA_SECRET_KEY": "<paste secret key>"
      }
    }
  }
}
```"""


def auth_setup_guide() -> str:
    """Return the full markdown setup guide. Single source of truth shared by the
    `setup_authentication` prompt and the 429 ToolError hint so they can't drift."""
    return (
        "## Setting up Internet Archive API keys\n\n"
        "Free API keys raise your Internet Archive rate-limit ceiling and remove "
        "the 429 errors. Keys never leave your machine — they live only in your "
        "client's MCP config and the wayback server subprocess's environment. "
        "Anthropic never sees them.\n\n"
        "### Steps\n\n"
        "**1. Get your keys.** Sign in at archive.org (free account) and visit "
        "<https://archive.org/account/s3.php>. Copy your access key and secret key.\n\n"
        "**2. Edit your MCP client's config.** The file depends on your client:\n\n"
        "- Claude Desktop (macOS): `~/Library/Application Support/Claude/claude_desktop_config.json`\n"
        "- Claude Desktop (Windows): `%APPDATA%\\Claude\\claude_desktop_config.json`\n"
        "- Claude Desktop (Linux): `~/.config/Claude/claude_desktop_config.json`\n"
        "- Claude Code (user): `~/.claude.json`\n"
        "- Claude Code (project): `./.mcp.json`\n"
        "- Cursor (project): `./.cursor/mcp.json`\n"
        "- Windsurf: `~/.codeium/windsurf/mcp_config.json`\n\n"
        "Open it in a text editor and replace the `wayback` entry with this exact block "
        "(paste your real keys where the placeholders are):\n\n"
        f"{AUTH_CONFIG_SNIPPET}\n\n"
        "If `mcpServers` already has other servers, just add the `env` block to your "
        "existing `wayback` entry — don't overwrite the whole file.\n\n"
        "**3. Restart your client.** Fully quit (⌘Q on macOS — closing the window "
        "isn't enough) and reopen. The server picks up the keys on next launch and "
        "authenticates every Internet Archive request from then on."
    )
