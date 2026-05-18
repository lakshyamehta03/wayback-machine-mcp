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
    ACCESS_KEY_ENV,
    CLIENTS,
    SECRET_KEY_ENV,
    SERVER_ENTRY,
    SERVER_KEY,
    clear_auth,
    get_client,
    install,
    pick_client_interactively,
    set_auth,
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


# ---------------------------------------------------------------------------
# set_auth / clear_auth
# ---------------------------------------------------------------------------


def _install_for_test(tmp_path: Path) -> Path:
    """Helper: stand up a fresh config with the wayback entry installed."""
    p = tmp_path / "config.json"
    install("claude-desktop", path=p)
    return p


def test_set_auth_writes_keys_into_env(tmp_path: Path) -> None:
    p = _install_for_test(tmp_path)

    rc = set_auth(
        "claude-desktop",
        path=p,
        access_key="ACCESS123",
        secret_key="SECRET456",
    )

    assert rc == 0
    data = _read(p)
    env = data["mcpServers"][SERVER_KEY]["env"]
    assert env[ACCESS_KEY_ENV] == "ACCESS123"
    assert env[SECRET_KEY_ENV] == "SECRET456"


def test_set_auth_preserves_other_env_vars(tmp_path: Path) -> None:
    p = _install_for_test(tmp_path)
    # Pre-seed an unrelated env var.
    data = _read(p)
    data["mcpServers"][SERVER_KEY]["env"] = {"CUSTOM_VAR": "keep-me"}
    p.write_text(json.dumps(data))

    set_auth("claude-desktop", path=p, access_key="A", secret_key="B")

    env = _read(p)["mcpServers"][SERVER_KEY]["env"]
    assert env["CUSTOM_VAR"] == "keep-me"
    assert env[ACCESS_KEY_ENV] == "A"
    assert env[SECRET_KEY_ENV] == "B"


def test_set_auth_strips_whitespace(tmp_path: Path) -> None:
    p = _install_for_test(tmp_path)

    set_auth(
        "claude-desktop",
        path=p,
        access_key="  ACCESS  \n",
        secret_key="\tSECRET\n",
    )

    env = _read(p)["mcpServers"][SERVER_KEY]["env"]
    assert env[ACCESS_KEY_ENV] == "ACCESS"
    assert env[SECRET_KEY_ENV] == "SECRET"


def test_set_auth_errors_when_wayback_not_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    p = tmp_path / "config.json"
    p.write_text("{}")  # exists but no wayback

    rc = set_auth("claude-desktop", path=p, access_key="A", secret_key="B")

    assert rc == 1
    err = capsys.readouterr().err
    assert "wayback isn't in" in err
    assert "--install" in err


def test_set_auth_errors_when_config_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    p = tmp_path / "nope.json"  # doesn't exist

    rc = set_auth("claude-desktop", path=p, access_key="A", secret_key="B")

    assert rc == 1
    assert "--install" in capsys.readouterr().err


def test_set_auth_works_for_zed_under_context_servers(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install("zed", path=p)

    set_auth("zed", path=p, access_key="ZA", secret_key="ZB")

    data = _read(p)
    env = data["context_servers"][SERVER_KEY]["env"]
    assert env[ACCESS_KEY_ENV] == "ZA"
    assert env[SECRET_KEY_ENV] == "ZB"


def test_set_auth_prompts_when_keys_not_passed(tmp_path: Path) -> None:
    p = _install_for_test(tmp_path)
    from io import StringIO

    stream_in = StringIO("MY_ACCESS\n")
    stream_out = StringIO()
    captured: list[str] = []

    def fake_read_secret(prompt: str) -> str:
        captured.append(prompt)
        return "MY_SECRET"

    rc = set_auth(
        "claude-desktop",
        path=p,
        stream_in=stream_in,
        stream_out=stream_out,
        read_secret=fake_read_secret,
    )

    assert rc == 0
    env = _read(p)["mcpServers"][SERVER_KEY]["env"]
    assert env[ACCESS_KEY_ENV] == "MY_ACCESS"
    assert env[SECRET_KEY_ENV] == "MY_SECRET"
    assert captured  # read_secret was actually used


def test_clear_auth_removes_keys_only(tmp_path: Path) -> None:
    p = _install_for_test(tmp_path)
    set_auth("claude-desktop", path=p, access_key="A", secret_key="B")
    # Also seed an unrelated env var.
    data = _read(p)
    data["mcpServers"][SERVER_KEY]["env"]["CUSTOM"] = "keep-me"
    p.write_text(json.dumps(data))

    rc = clear_auth("claude-desktop", path=p)

    assert rc == 0
    env = _read(p)["mcpServers"][SERVER_KEY]["env"]
    assert ACCESS_KEY_ENV not in env
    assert SECRET_KEY_ENV not in env
    assert env["CUSTOM"] == "keep-me"


def test_clear_auth_removes_empty_env_block(tmp_path: Path) -> None:
    p = _install_for_test(tmp_path)
    set_auth("claude-desktop", path=p, access_key="A", secret_key="B")

    clear_auth("claude-desktop", path=p)

    entry = _read(p)["mcpServers"][SERVER_KEY]
    assert "env" not in entry


def test_clear_auth_when_no_keys_set_is_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    p = _install_for_test(tmp_path)

    rc = clear_auth("claude-desktop", path=p)

    assert rc == 0
    assert "nothing to clear" in capsys.readouterr().out


def test_clear_auth_missing_config_is_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = clear_auth("claude-desktop", path=tmp_path / "nope.json")

    assert rc == 0
    assert "nothing to clear" in capsys.readouterr().out


def test_install_prints_set_auth_hint_when_no_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    install("claude-desktop", path=tmp_path / "c.json")

    out = capsys.readouterr().out
    assert "--set-auth" in out
    assert "archive.org/account/s3.php" in out


# ---------------------------------------------------------------------------
# Matching wayback entries by command, not by key name (issue #22)
# ---------------------------------------------------------------------------


def test_uninstall_removes_uvx_entry_under_custom_key(tmp_path: Path) -> None:
    """A user who installed manually under e.g. `wayback-mcp` should still be
    cleanable via --uninstall --force, since the entry's `command`/`args`
    identifies it as our server."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                    "other": {"command": "x"},
                }
            }
        )
    )

    rc = uninstall("claude-code-user", path=cfg, force=True)

    assert rc == 0
    data = _read(cfg)
    assert "wayback-mcp" not in data["mcpServers"]
    assert data["mcpServers"]["other"] == {"command": "x"}


def test_uninstall_removes_direct_command_entry(tmp_path: Path) -> None:
    """An entry whose command IS `mcp-server-wayback` directly (no uvx wrapper)
    should also be matched."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "my-wayback": {"command": "mcp-server-wayback", "args": []},
                }
            }
        )
    )

    rc = uninstall("claude-code-user", path=cfg, force=True)

    assert rc == 0
    assert "mcpServers" not in _read(cfg)


def test_uninstall_removes_uv_run_local_dev_entry(tmp_path: Path) -> None:
    """`uv run mcp-server-wayback` from a local checkout should match too."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-dev": {"command": "uv", "args": ["run", "mcp-server-wayback"]},
                }
            }
        )
    )

    rc = uninstall("claude-code-user", path=cfg, force=True)

    assert rc == 0
    assert "mcpServers" not in _read(cfg)


def test_uninstall_does_not_match_unrelated_uvx_entry(tmp_path: Path) -> None:
    """A `uvx some-other-server` entry must not be mistaken for ours."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"command": "uvx", "args": ["mcp-server-other"]},
                }
            }
        )
    )

    rc = uninstall("claude-code-user", path=cfg, force=True)

    assert rc == 0
    assert _read(cfg)["mcpServers"]["other"]["command"] == "uvx"


def test_uninstall_prompts_for_confirmation_on_non_default_key(
    tmp_path: Path,
) -> None:
    """Without --force, removing an entry under a non-default key should
    require explicit confirmation."""
    from io import StringIO

    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                }
            }
        )
    )

    stream_in = StringIO("n\n")
    stream_out = StringIO()
    rc = uninstall(
        "claude-code-user", path=cfg, stream_in=stream_in, stream_out=stream_out
    )

    assert rc == 0
    assert "wayback-mcp" in _read(cfg)["mcpServers"]  # not removed
    assert "wayback-mcp" in stream_out.getvalue()
    assert "Cancelled" in stream_out.getvalue()


def test_uninstall_confirmation_yes_removes_entry(tmp_path: Path) -> None:
    from io import StringIO

    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                }
            }
        )
    )

    stream_in = StringIO("y\n")
    stream_out = StringIO()
    rc = uninstall(
        "claude-code-user", path=cfg, stream_in=stream_in, stream_out=stream_out
    )

    assert rc == 0
    assert "mcpServers" not in _read(cfg)


def test_uninstall_force_skips_confirmation(tmp_path: Path) -> None:
    """--force should remove non-default-key entries without prompting."""
    from io import StringIO

    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                }
            }
        )
    )

    # Empty stream_in proves we never read from it.
    stream_in = StringIO("")
    stream_out = StringIO()
    rc = uninstall(
        "claude-code-user",
        path=cfg,
        force=True,
        stream_in=stream_in,
        stream_out=stream_out,
    )

    assert rc == 0
    assert "mcpServers" not in _read(cfg)


def test_uninstall_default_key_still_works_without_prompt(tmp_path: Path) -> None:
    """The canonical `wayback` key must continue to uninstall silently —
    no confirmation prompt was needed before, none should be now."""
    from io import StringIO

    cfg = tmp_path / "claude.json"
    install("claude-code-user", path=cfg)

    stream_in = StringIO("")  # no input available — would hang if prompted
    stream_out = StringIO()
    rc = uninstall(
        "claude-code-user", path=cfg, stream_in=stream_in, stream_out=stream_out
    )

    assert rc == 0
    assert "mcpServers" not in _read(cfg)


def test_uninstall_removes_both_default_and_custom_keys(tmp_path: Path) -> None:
    """If both the canonical `wayback` key and a custom-named entry exist,
    --force --uninstall should remove both."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_KEY: SERVER_ENTRY,
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                }
            }
        )
    )

    rc = uninstall("claude-code-user", path=cfg, force=True)

    assert rc == 0
    assert "mcpServers" not in _read(cfg)


def test_set_auth_works_on_custom_key_name(tmp_path: Path) -> None:
    """set_auth should locate the wayback entry by invocation when the user
    installed under a non-default key name."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                }
            }
        )
    )

    rc = set_auth("claude-code-user", path=cfg, access_key="A", secret_key="B")

    assert rc == 0
    env = _read(cfg)["mcpServers"]["wayback-mcp"]["env"]
    assert env[ACCESS_KEY_ENV] == "A"
    assert env[SECRET_KEY_ENV] == "B"


def test_clear_auth_works_on_custom_key_name(tmp_path: Path) -> None:
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {
                        "command": "uvx",
                        "args": ["mcp-server-wayback"],
                        "env": {ACCESS_KEY_ENV: "A", SECRET_KEY_ENV: "B"},
                    },
                }
            }
        )
    )

    rc = clear_auth("claude-code-user", path=cfg)

    assert rc == 0
    entry = _read(cfg)["mcpServers"]["wayback-mcp"]
    assert "env" not in entry


def test_set_auth_errors_on_ambiguous_multiple_custom_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """If two non-default-key entries both look like our server (and no
    canonical `wayback` key exists), set_auth should refuse rather than
    silently picking one."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                    "wayback-dev": {"command": "uv", "args": ["run", "mcp-server-wayback"]},
                }
            }
        )
    )

    rc = set_auth("claude-code-user", path=cfg, access_key="A", secret_key="B")

    assert rc == 1
    err = capsys.readouterr().err
    assert "multiple" in err.lower()
    assert "wayback-mcp" in err
    assert "wayback-dev" in err


def test_set_auth_prefers_canonical_key_when_both_exist(tmp_path: Path) -> None:
    """If both `wayback` and a custom-named entry exist, set_auth should
    target the canonical one (preserves pre-existing behavior)."""
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_KEY: dict(SERVER_ENTRY),
                    "wayback-mcp": {"command": "uvx", "args": ["mcp-server-wayback"]},
                }
            }
        )
    )

    rc = set_auth("claude-code-user", path=cfg, access_key="A", secret_key="B")

    assert rc == 0
    data = _read(cfg)
    assert data["mcpServers"][SERVER_KEY]["env"][ACCESS_KEY_ENV] == "A"
    assert "env" not in data["mcpServers"]["wayback-mcp"]
