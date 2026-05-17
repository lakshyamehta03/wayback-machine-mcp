"""One-shot installer that wires this server into Claude Desktop's config.

Invoked via the `--install` / `--uninstall` flags on the package's console
script. Detects the right OS-specific config path, merges the wayback entry
into the existing `mcpServers` block (preserving anything else there), and
prints a restart hint.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

SERVER_KEY = "wayback"
SERVER_ENTRY = {
    "command": "uvx",
    "args": ["mcp-server-wayback"],
}


def claude_desktop_config_path() -> Path:
    """Return the platform-specific path to claude_desktop_config.json."""
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
    # Linux / fallback
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    return json.loads(text)


def install(path: Path | None = None, *, force: bool = False) -> int:
    """Add the wayback entry to Claude Desktop's config. Returns an exit code."""
    config_path = path or claude_desktop_config_path()

    try:
        config = _load_config(config_path)
    except json.JSONDecodeError as e:
        print(
            f"error: {config_path} exists but isn't valid JSON ({e}).\n"
            "Fix the file or move it aside, then retry.",
            file=sys.stderr,
        )
        return 1

    servers = config.setdefault("mcpServers", {})
    if SERVER_KEY in servers and not force:
        print(f"wayback is already configured in {config_path}.")
        print("Re-run with --uninstall first if you want to reinstall.")
        return 0

    servers[SERVER_KEY] = SERVER_ENTRY
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    print(f"✓ Added wayback to {config_path}")
    print("Restart Claude Desktop to load it (⌘Q on macOS, then reopen).")
    return 0


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
        "Claude Desktop config and the wayback server subprocess's environment. "
        "Anthropic never sees them.\n\n"
        "### Steps\n\n"
        "**1. Get your keys.** Sign in at archive.org (free account) and visit "
        "<https://archive.org/account/s3.php>. Copy your access key and secret key.\n\n"
        "**2. Edit your Claude Desktop config.** The file lives at:\n\n"
        "- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`\n"
        "- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`\n"
        "- Linux: `~/.config/Claude/claude_desktop_config.json`\n\n"
        "Open it in a text editor and replace the `wayback` entry with this exact block "
        "(paste your real keys where the placeholders are):\n\n"
        f"{AUTH_CONFIG_SNIPPET}\n\n"
        "If `mcpServers` already has other servers, just add the `env` block to your "
        "existing `wayback` entry — don't overwrite the whole file.\n\n"
        "**3. Restart Claude Desktop.** Fully quit (⌘Q on macOS — closing the window "
        "isn't enough) and reopen. The server picks up the keys on next launch and "
        "authenticates every Internet Archive request from then on."
    )


def uninstall(path: Path | None = None) -> int:
    """Remove the wayback entry from Claude Desktop's config. Returns an exit code."""
    config_path = path or claude_desktop_config_path()

    if not config_path.exists():
        print(f"No config at {config_path} — nothing to remove.")
        return 0

    try:
        config = _load_config(config_path)
    except json.JSONDecodeError as e:
        print(f"error: {config_path} isn't valid JSON ({e}).", file=sys.stderr)
        return 1

    servers = config.get("mcpServers", {})
    if SERVER_KEY not in servers:
        print(f"wayback isn't in {config_path} — nothing to remove.")
        return 0

    del servers[SERVER_KEY]
    if not servers:
        del config["mcpServers"]
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    print(f"✓ Removed wayback from {config_path}")
    print("Restart Claude Desktop for the change to take effect.")
    return 0
