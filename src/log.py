"""Event log gated by WAYBACK_MCP_LOG=debug.

Off by default. Writes to stderr unless WAYBACK_MCP_LOG_FILE is set, in which
case it appends to that file. Stdout is never used (it's reserved for MCP
stdio framing). Each event is one line with monotonic-clock timestamp and
key=value fields, so a stuck call shows up as a missing follow-up line.
"""
import os
import sys
import time
from typing import IO

_DEBUG = os.environ.get("WAYBACK_MCP_LOG", "").lower() == "debug"
_LOG_FILE_PATH = os.environ.get("WAYBACK_MCP_LOG_FILE", "").strip()
_START = time.monotonic()


def _open_sink() -> IO[str]:
    if _LOG_FILE_PATH:
        try:
            return open(_LOG_FILE_PATH, "a", buffering=1)  # line-buffered
        except OSError as exc:
            print(
                f"[wayback-mcp] could not open WAYBACK_MCP_LOG_FILE={_LOG_FILE_PATH!r}: {exc}; "
                "falling back to stderr",
                file=sys.stderr,
                flush=True,
            )
    return sys.stderr


_sink: IO[str] = _open_sink() if _DEBUG else sys.stderr


def is_enabled() -> bool:
    return _DEBUG


def log(event: str, **fields: object) -> None:
    if not _DEBUG:
        return
    elapsed = time.monotonic() - _START
    parts = [f"[{elapsed:8.3f}s]", event]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    print(" ".join(parts), file=_sink, flush=True)
