"""Stderr-based event log gated by WAYBACK_MCP_LOG=debug.

Off by default. Writes to stderr (stdout is reserved for MCP stdio framing).
Each event is one line with monotonic-clock timestamp and key=value fields,
so a stuck call shows up as a missing follow-up line.
"""
import os
import sys
import time

_DEBUG = os.environ.get("WAYBACK_MCP_LOG", "").lower() == "debug"
_START = time.monotonic()


def is_enabled() -> bool:
    return _DEBUG


def log(event: str, **fields: object) -> None:
    if not _DEBUG:
        return
    elapsed = time.monotonic() - _START
    parts = [f"[{elapsed:8.3f}s]", event]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    print(" ".join(parts), file=sys.stderr, flush=True)
