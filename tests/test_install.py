"""Unit tests for the --install / --uninstall config-merge helper.

Covers the merge path (preserves siblings), idempotency (already-installed
is a no-op), --force (overwrite), uninstall round-trip, missing-config
handling, and corrupt-JSON refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wayback_mcp.install import SERVER_ENTRY, SERVER_KEY, install, uninstall


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
