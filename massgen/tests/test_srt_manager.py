"""Unit tests for SrtManager — OS-level SRT (sandbox-runtime) sandboxing.

These tests are pure/offline: they never require the `srt` binary or bubblewrap.
They cover:
  - settings derivation from PathPermissionManager (defense-in-depth: SRT settings
    derive from the SAME path policy as the app-level permission layer)
  - the two profiles ("execution" tight; "fs_tools" widened for snapshots)
  - network deny-all-by-default with opt-in allowlist (capability grant)
  - command/argv wrapping (single source of truth shared with the MCP server)
  - availability/platform guards
"""

import json

import pytest

from massgen.filesystem_manager._base import Permission
from massgen.filesystem_manager._path_permission_manager import PathPermissionManager
from massgen.filesystem_manager._srt_manager import (
    SrtManager,
    srt_available,
    wrap_argv_with_srt,
    wrap_command_with_srt,
)


@pytest.fixture
def pm_with_paths(tmp_path):
    """A PathPermissionManager populated like a real agent setup."""
    workspace = tmp_path / "workspace"
    temp_ws = tmp_path / "temp_ws"
    ctx_write = tmp_path / "ctx_write"
    ctx_read = tmp_path / "ctx_read"
    protected = ctx_write / "secrets"
    for d in (workspace, temp_ws, ctx_write, ctx_read, protected):
        d.mkdir(parents=True, exist_ok=True)

    pm = PathPermissionManager(context_write_access_enabled=True)
    pm.add_path(workspace, Permission.WRITE, "workspace")
    pm.add_path(temp_ws, Permission.READ, "temp_workspace")
    pm.add_context_paths(
        [
            {"path": str(ctx_write), "permission": "write", "protected_paths": ["secrets"]},
            {"path": str(ctx_read), "permission": "read"},
        ],
    )
    return {
        "pm": pm,
        "workspace": workspace.resolve(),
        "temp_ws": temp_ws.resolve(),
        "ctx_write": ctx_write.resolve(),
        "ctx_read": ctx_read.resolve(),
        "protected": protected.resolve(),
    }


# --------------------------------------------------------------------------- #
# build_settings — execution profile
# --------------------------------------------------------------------------- #
def test_execution_profile_workspace_and_write_context_are_writable(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"])
    settings = mgr.build_settings(profile="execution")
    allow_write = settings["filesystem"]["allowWrite"]
    assert str(pm_with_paths["workspace"]) in allow_write
    assert str(pm_with_paths["ctx_write"]) in allow_write


def test_execution_profile_temp_and_read_context_are_not_writable(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"])
    settings = mgr.build_settings(profile="execution")
    allow_write = settings["filesystem"]["allowWrite"]
    deny_write = settings["filesystem"]["denyWrite"]
    # Temp workspace is read-only for the agent during coordination.
    assert str(pm_with_paths["temp_ws"]) not in allow_write
    assert str(pm_with_paths["temp_ws"]) in deny_write
    assert str(pm_with_paths["ctx_read"]) in deny_write


def test_protected_paths_are_deny_read(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"], extra_deny_read=["/some/extra/secret"])
    settings = mgr.build_settings(profile="execution")
    deny_read = settings["filesystem"]["denyRead"]
    assert str(pm_with_paths["protected"]) in deny_read
    assert "/some/extra/secret" in deny_read


def test_protected_paths_are_also_deny_write(pm_with_paths):
    # Protected paths are immune from modification even inside a writable context.
    mgr = SrtManager(pm_with_paths["pm"])
    settings = mgr.build_settings(profile="execution")
    assert str(pm_with_paths["protected"]) in settings["filesystem"]["denyWrite"]


def test_secret_stores_are_deny_read_by_default(pm_with_paths):
    # SRT reads are allow-all by default; the manager must deny known secret stores
    # so a sandboxed `cat ~/.ssh/id_rsa` is blocked.
    from pathlib import Path

    mgr = SrtManager(pm_with_paths["pm"])
    deny_read = mgr.build_settings(profile="execution")["filesystem"]["denyRead"]
    home = Path.home()
    for rel in (".ssh", ".aws", ".gnupg", ".config/gcloud"):
        assert str(home / rel) in deny_read, f"{rel} should be read-denied by default"
    assert "/etc/shadow" in deny_read


# --------------------------------------------------------------------------- #
# build_settings — fs_tools profile (defense in depth, must allow snapshots)
# --------------------------------------------------------------------------- #
def test_fs_tools_profile_widens_writes_for_temp_and_snapshot(pm_with_paths, tmp_path):
    snapshot = tmp_path / "snapshot_storage"
    snapshot.mkdir()
    mgr = SrtManager(pm_with_paths["pm"], fs_tools_extra_writable=[snapshot])
    settings = mgr.build_settings(profile="fs_tools")
    allow_write = settings["filesystem"]["allowWrite"]
    # The fs-tools SERVER must be able to write workspace + temp + snapshot_storage,
    # even though the AGENT sees temp as read-only.
    assert str(pm_with_paths["workspace"]) in allow_write
    assert str(pm_with_paths["temp_ws"]) in allow_write
    assert str(snapshot.resolve()) in allow_write


# --------------------------------------------------------------------------- #
# network — deny-all by default, opt-in allowlist
# --------------------------------------------------------------------------- #
def test_network_default_deny_all(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"])
    settings = mgr.build_settings(profile="execution")
    assert settings["network"]["allowedDomains"] == []


def test_network_allowlist_is_opt_in(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"], network_allowed_domains=["api.anthropic.com"])
    settings = mgr.build_settings(profile="execution")
    assert settings["network"]["allowedDomains"] == ["api.anthropic.com"]


def test_allow_unix_sockets_passthrough(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"], allow_unix_sockets=["/var/run/docker.sock"])
    settings = mgr.build_settings(profile="execution")
    assert settings["network"]["allowUnixSockets"] == ["/var/run/docker.sock"]


# --------------------------------------------------------------------------- #
# write_settings_file
# --------------------------------------------------------------------------- #
def test_write_settings_file_produces_valid_json(pm_with_paths, tmp_path):
    mgr = SrtManager(pm_with_paths["pm"], settings_dir=tmp_path / "srt")
    path = mgr.write_settings_file(profile="execution", agent_id="agent_a")
    assert path.exists()
    data = json.loads(path.read_text())
    assert "filesystem" in data and "network" in data
    assert str(pm_with_paths["workspace"]) in data["filesystem"]["allowWrite"]


# --------------------------------------------------------------------------- #
# wrapping — single source of truth shared with the MCP server
# --------------------------------------------------------------------------- #
def test_wrap_command_string_form():
    assert wrap_command_with_srt("echo hi", "/tmp/cfg.json") == "srt --settings /tmp/cfg.json sh -c 'echo hi'"


def test_wrap_command_quotes_shell_metacharacters():
    wrapped = wrap_command_with_srt("echo hi | grep h", "/tmp/cfg.json")
    # The original command must be passed as a single quoted argument to `sh -c`,
    # so the pipe runs INSIDE the sandbox, not in the outer (unsandboxed) shell.
    assert wrapped == "srt --settings /tmp/cfg.json sh -c 'echo hi | grep h'"


def test_wrap_argv_list_form():
    assert wrap_argv_with_srt(["codex", "exec", "--json"], "/tmp/cfg.json") == [
        "srt",
        "--settings",
        "/tmp/cfg.json",
        "codex",
        "exec",
        "--json",
    ]


def test_custom_srt_binary_path():
    assert wrap_argv_with_srt(["x"], "/c.json", srt_path="/opt/srt")[0] == "/opt/srt"


# --------------------------------------------------------------------------- #
# availability / platform guards
# --------------------------------------------------------------------------- #
def test_srt_available_false_when_missing(monkeypatch):
    monkeypatch.setattr("massgen.filesystem_manager._srt_manager.shutil.which", lambda _: None)
    assert srt_available() is False


def test_verify_available_raises_actionable_error_when_missing(monkeypatch, pm_with_paths):
    monkeypatch.setattr("massgen.filesystem_manager._srt_manager.platform.system", lambda: "Darwin")
    monkeypatch.setattr("massgen.filesystem_manager._srt_manager.shutil.which", lambda _: None)
    mgr = SrtManager(pm_with_paths["pm"])
    with pytest.raises(RuntimeError, match="sandbox-runtime"):
        mgr.verify_available()


def test_verify_available_raises_on_windows(monkeypatch, pm_with_paths):
    monkeypatch.setattr("massgen.filesystem_manager._srt_manager.platform.system", lambda: "Windows")
    monkeypatch.setattr("massgen.filesystem_manager._srt_manager.shutil.which", lambda _: "C:/srt.exe")
    mgr = SrtManager(pm_with_paths["pm"])
    with pytest.raises(RuntimeError, match="(?i)windows"):
        mgr.verify_available()
