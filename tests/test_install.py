"""Unit tests for the --install / --uninstall config-merge helper.

Covers the merge path (preserves siblings), idempotency (already-installed
is a no-op), --force (overwrite), uninstall round-trip, missing-config
handling, and corrupt-JSON refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wayback_mcp.install import (
    CLIENTS,
    SERVER_ENTRY,
    SERVER_KEY,
    get_client,
    install,
    pick_client_interactively,
    uninstall,
)


def _read(p: Path) -> dict:
    return json.loads(p.read_text())


def test_install_into_missing_file_creates_it(tmp_path: Path) -> None:
    cfg = tmp_path / "nested" / "claude_desktop_config.json"

    rc = install(path=cfg)

    assert rc == 0
    assert cfg.exists()
    assert _read(cfg) == {"mcpServers": {SERVER_KEY: SERVER_ENTRY}}


def test_install_preserves_existing_servers(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))

    rc = install(path=cfg)

    assert rc == 0
    data = _read(cfg)
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"][SERVER_KEY] == SERVER_ENTRY


def test_install_preserves_unrelated_top_level_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"someOtherSetting": True, "mcpServers": {}}))

    install(path=cfg)

    assert _read(cfg)["someOtherSetting"] is True


def test_install_is_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    cfg = tmp_path / "claude_desktop_config.json"

    install(path=cfg)
    capsys.readouterr()  # drop first-install output
    rc = install(path=cfg)

    assert rc == 0
    assert "already configured" in capsys.readouterr().out
    # entry shape unchanged
    assert _read(cfg)["mcpServers"][SERVER_KEY] == SERVER_ENTRY


def test_install_force_overwrites_existing_entry(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(
        json.dumps({"mcpServers": {SERVER_KEY: {"command": "stale", "args": []}}})
    )

    rc = install(path=cfg, force=True)

    assert rc == 0
    assert _read(cfg)["mcpServers"][SERVER_KEY] == SERVER_ENTRY


def test_install_refuses_corrupt_json(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{ not json")

    rc = install(path=cfg)

    assert rc == 1
    assert "isn't valid JSON" in capsys.readouterr().err
    # corrupt file is not overwritten
    assert cfg.read_text() == "{ not json"


def test_uninstall_round_trips(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))

    install(path=cfg)
    uninstall(path=cfg)

    # 'other' server preserved, wayback gone
    assert _read(cfg) == {"mcpServers": {"other": {"command": "x"}}}


def test_uninstall_drops_empty_mcpservers_block(tmp_path: Path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    install(path=cfg)

    uninstall(path=cfg)

    assert "mcpServers" not in _read(cfg)


def test_uninstall_missing_file_is_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"

    rc = uninstall(path=cfg)

    assert rc == 0
    assert "nothing to remove" in capsys.readouterr().out
    assert not cfg.exists()


def test_uninstall_when_not_installed_is_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))

    rc = uninstall(path=cfg)

    assert rc == 0
    assert "nothing to remove" in capsys.readouterr().out
    assert _read(cfg) == {"mcpServers": {"other": {"command": "x"}}}


# ---------------------------------------------------------------------------
# Multi-client install/uninstall coverage
# ---------------------------------------------------------------------------


def test_install_unknown_client_returns_error_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = install("not-a-real-client", path=tmp_path / "cfg.json")

    assert rc == 2
    assert "unknown client" in capsys.readouterr().err


def test_install_writes_zed_under_context_servers_not_mcpservers(
    tmp_path: Path,
) -> None:
    """Zed uses `context_servers` as its top-level key. The installer must
    respect that — writing to `mcpServers` would silently no-op in Zed."""
    cfg = tmp_path / "zed-settings.json"
    cfg.write_text(json.dumps({"theme": "Dark", "context_servers": {}}))

    install("zed", path=cfg)

    data = _read(cfg)
    assert data["theme"] == "Dark"  # unrelated settings preserved
    assert data["context_servers"][SERVER_KEY] == SERVER_ENTRY
    assert "mcpServers" not in data  # wrong key not introduced


def test_uninstall_zed_drops_context_servers_when_empty(tmp_path: Path) -> None:
    cfg = tmp_path / "zed-settings.json"
    cfg.write_text(json.dumps({"theme": "Dark"}))

    install("zed", path=cfg)
    uninstall("zed", path=cfg)

    data = _read(cfg)
    assert data == {"theme": "Dark"}


def test_install_each_mcpservers_client_writes_to_mcpservers(tmp_path: Path) -> None:
    """All non-Zed clients share the `mcpServers` container — verify each works
    against an injected path. Catches typos in the registry."""
    for client in CLIENTS:
        if client.container_key != "mcpServers":
            continue
        cfg = tmp_path / f"{client.key}.json"
        rc = install(client.key, path=cfg)
        assert rc == 0, f"{client.key} install failed"
        assert _read(cfg)["mcpServers"][SERVER_KEY] == SERVER_ENTRY


def test_get_client_returns_none_for_unknown_key() -> None:
    assert get_client("nope") is None


def test_get_client_returns_matching_record() -> None:
    c = get_client("claude-desktop")
    assert c is not None
    assert c.label == "Claude Desktop"


# ---------------------------------------------------------------------------
# Interactive picker
# ---------------------------------------------------------------------------


def test_pick_client_returns_chosen_client(capsys: pytest.CaptureFixture) -> None:
    from io import StringIO

    # Pick option 1 (claude-desktop)
    stream_in = StringIO("1\n")
    stream_out = StringIO()

    result = pick_client_interactively(stream_in=stream_in, stream_out=stream_out)

    assert result is not None
    assert result.key == "claude-desktop"


def test_pick_client_returns_none_on_cancel() -> None:
    from io import StringIO

    cancel_index = len(CLIENTS) + 1
    stream_in = StringIO(f"{cancel_index}\n")
    stream_out = StringIO()

    result = pick_client_interactively(stream_in=stream_in, stream_out=stream_out)

    assert result is None


def test_pick_client_reprompts_on_invalid_input() -> None:
    from io import StringIO

    # 'abc' → re-prompt, '99' → re-prompt (out of range), '2' → claude-code-user
    stream_in = StringIO("abc\n99\n2\n")
    stream_out = StringIO()

    result = pick_client_interactively(stream_in=stream_in, stream_out=stream_out)

    assert result is not None
    assert result.key == "claude-code-user"
    assert "Please enter a number" in stream_out.getvalue()


def test_pick_client_returns_none_on_eof() -> None:
    from io import StringIO

    stream_in = StringIO("")  # immediate EOF
    stream_out = StringIO()

    result = pick_client_interactively(stream_in=stream_in, stream_out=stream_out)

    assert result is None
