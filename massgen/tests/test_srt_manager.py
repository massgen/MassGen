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


def test_protected_paths_are_also_deny_write(pm_with_paths):
    # Protected paths are immune from modification even inside a writable context.
    mgr = SrtManager(pm_with_paths["pm"])
    settings = mgr.build_settings(profile="execution")
    assert str(pm_with_paths["protected"]) in settings["filesystem"]["denyWrite"]


# --------------------------------------------------------------------------- #
# Read-confinement modes (SRT reads are allow-all by default; allowRead WINS)
# --------------------------------------------------------------------------- #
def test_default_read_mode_is_confined(pm_with_paths):
    assert SrtManager(pm_with_paths["pm"]).read_mode == "confined"


def test_confined_mode_denies_home_allows_managed(pm_with_paths):
    from pathlib import Path

    mgr = SrtManager(pm_with_paths["pm"])  # default confined
    fs = mgr.build_settings(profile="execution")["filesystem"]
    # $HOME denied (covers ~/.ssh, ~/.aws, other projects, personal data)…
    assert str(Path.home()) in fs["denyRead"]
    assert "/etc/shadow" in fs["denyRead"]
    # …but the agent's managed paths are re-allowed (allowRead wins over denyRead).
    assert str(pm_with_paths["workspace"]) in fs["allowRead"]
    assert str(pm_with_paths["ctx_read"]) in fs["allowRead"]


def test_strict_mode_denies_root_allows_managed_and_system(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"], read_mode="strict")
    fs = mgr.build_settings(profile="execution")["filesystem"]
    assert fs["denyRead"] == ["/"]
    assert str(pm_with_paths["workspace"]) in fs["allowRead"]
    assert "/usr" in fs["allowRead"]  # system baseline so commands can run


def test_open_mode_uses_secret_denylist(pm_with_paths):
    from pathlib import Path

    mgr = SrtManager(pm_with_paths["pm"], read_mode="open", extra_deny_read=["/some/extra/secret"])
    fs = mgr.build_settings(profile="execution")["filesystem"]
    home = Path.home()
    for rel in (".ssh", ".aws", ".gnupg"):
        assert str(home / rel) in fs["denyRead"]
    # protected + extras are read-denied in open mode (nothing re-allows them).
    assert str(pm_with_paths["protected"]) in fs["denyRead"]
    assert "/some/extra/secret" in fs["denyRead"]
    assert fs["allowRead"] == []


def test_allow_read_extras_propagate(pm_with_paths):
    mgr = SrtManager(pm_with_paths["pm"], allow_read=["/opt/shared-cache"])
    fs = mgr.build_settings(profile="execution")["filesystem"]
    assert "/opt/shared-cache" in fs["allowRead"]


def test_invalid_read_mode_falls_back_to_confined(pm_with_paths):
    assert SrtManager(pm_with_paths["pm"], read_mode="bogus").read_mode == "confined"


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


def _is_read_allowed(allow_read, target: str) -> bool:
    """True if `target` is covered by some allowRead root (itself or an ancestor)."""
    from pathlib import Path as _P

    t = _P(target).resolve()
    for root in allow_read:
        r = _P(root).resolve()
        if t == r or r in t.parents:
            return True
    return False


def test_fs_tools_profile_confined_allows_reading_framework_runtime(pm_with_paths):
    """REGRESSION: when SRT wraps a framework MCP server (fastmcp run <massgen script>),
    confined mode denies all of $HOME — but the venv (fastmcp + deps + interpreter) and
    the massgen package source both live under $HOME. Without re-allowing the framework's
    own read roots, `srt` denies reading the server's own code and the server can't start
    ("Operation not permitted: _workspace_tools_server.py"). The fs_tools profile must
    re-allow the framework runtime roots so the wrapped server can read its own code while
    $HOME otherwise stays denied.
    """
    import sys
    from pathlib import Path

    import massgen

    mgr = SrtManager(pm_with_paths["pm"])  # default confined
    fs = mgr.build_settings(profile="fs_tools")["filesystem"]

    # $HOME is still denied (we didn't just open everything back up).
    assert str(Path.home()) in fs["denyRead"]

    # The framework's own code + interpreter + deps must be readable (allowRead wins).
    massgen_dir = Path(massgen.__file__).resolve().parent
    assert _is_read_allowed(fs["allowRead"], str(massgen_dir)), "massgen package dir must be readable by the wrapped fs-tools server"
    assert _is_read_allowed(fs["allowRead"], sys.prefix), "Python prefix (venv: fastmcp + deps) must be readable"
    assert _is_read_allowed(fs["allowRead"], sys.base_prefix), "base Python prefix must be readable"

    # git is core to the workspace model (GitPython reads ~/.gitconfig at import), so
    # its user config must be readable too — else the server crashes on import under
    # confined ("unable to access '~/.gitconfig': Operation not permitted").
    assert _is_read_allowed(fs["allowRead"], str(Path.home() / ".gitconfig")), "git user config must be readable by the wrapped fs-tools server"


def test_execution_profile_does_not_widen_for_framework_runtime(pm_with_paths):
    """The framework-runtime re-allow is fs_tools-only: the agent's own command sandbox
    (execution profile) stays tight and must NOT gain the massgen package dir just because
    fs_tools needs it."""
    from pathlib import Path

    import massgen

    mgr = SrtManager(pm_with_paths["pm"])  # default confined
    fs = mgr.build_settings(profile="execution")["filesystem"]
    massgen_dir = str(Path(massgen.__file__).resolve().parent)
    assert massgen_dir not in fs["allowRead"]


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
