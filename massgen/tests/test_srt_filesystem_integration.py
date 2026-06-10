"""FilesystemManager ↔ SRT wiring tests (offline; no `srt` binary required).

Covers the config-building side of SRT mode:
  - command-line MCP server gets `--execution-mode srt --srt-settings <path>`
    and a valid settings file is generated from the path policy
  - the filesystem-tools MCP server is ALSO srt-wrapped (defense in depth)
  - default (local) mode is completely unchanged
"""

import json
from pathlib import Path

import pytest

from massgen.filesystem_manager._filesystem_manager import FilesystemManager


@pytest.fixture
def srt_fs_manager(tmp_path):
    return FilesystemManager(
        cwd=str(tmp_path / "workspace"),
        enable_mcp_command_line=True,
        command_line_execution_mode="srt",
        command_line_srt_network_allowed_domains=["api.anthropic.com"],
    )


@pytest.fixture
def local_fs_manager(tmp_path):
    return FilesystemManager(
        cwd=str(tmp_path / "workspace"),
        enable_mcp_command_line=True,
        command_line_execution_mode="local",
    )


# --------------------------------------------------------------------------- #
# command-line MCP server
# --------------------------------------------------------------------------- #
def test_command_line_config_has_srt_args(srt_fs_manager):
    config = srt_fs_manager.get_command_line_mcp_config()
    args = config["args"]
    assert "--execution-mode" in args
    assert args[args.index("--execution-mode") + 1] == "srt"
    assert "--srt-settings" in args


def test_command_line_config_writes_valid_settings_file(srt_fs_manager):
    config = srt_fs_manager.get_command_line_mcp_config()
    settings_path = Path(config["args"][config["args"].index("--srt-settings") + 1])
    assert settings_path.exists()
    data = json.loads(settings_path.read_text())
    # Workspace is writable; the opt-in network allowlist is honored.
    assert str(srt_fs_manager.cwd) in data["filesystem"]["allowWrite"]
    assert data["network"]["allowedDomains"] == ["api.anthropic.com"]


def test_local_mode_has_no_srt_args(local_fs_manager):
    config = local_fs_manager.get_command_line_mcp_config()
    assert "--srt-settings" not in config["args"]
    assert config["args"][config["args"].index("--execution-mode") + 1] == "local"


# --------------------------------------------------------------------------- #
# filesystem-tools MCP server (defense in depth) — srt-wrapped via the `sh -c`
# form so srt cannot eat the server's `--` separator (which broke the handshake
# in the direct-argv form). Must keep the workspace writable + pass MCP security.
# --------------------------------------------------------------------------- #
def test_fs_tools_server_is_srt_wrapped_via_sh_c(srt_fs_manager):
    config = srt_fs_manager.get_workspace_tools_mcp_config()
    assert config["command"] == "srt"
    assert config["args"][0] == "--settings"
    fs_settings = Path(config["args"][1])
    assert fs_settings.exists()
    # CRITICAL: sh -c form, with the original fastmcp command line (incl. `--`)
    # preserved inside the shell string.
    assert config["args"][2] == "sh"
    assert config["args"][3] == "-c"
    inner = config["args"][4]
    assert inner.startswith("fastmcp run ")
    assert " -- --allowed-paths " in inner  # the `--` separator survives
    data = json.loads(fs_settings.read_text())
    assert str(srt_fs_manager.cwd) in data["filesystem"]["allowWrite"]


def test_fs_tools_server_not_wrapped_in_local_mode(local_fs_manager):
    config = local_fs_manager.get_workspace_tools_mcp_config()
    assert config["command"] == "fastmcp"
    assert config["args"][0] == "run"


# --------------------------------------------------------------------------- #
# MCP security allowlist — `srt` must be an accepted MCP server executable, and
# the wrapped config must pass full security validation.
# Regression origin: a live smoke test, not the dict-shape tests above.
# --------------------------------------------------------------------------- #
def test_srt_is_an_allowed_mcp_executable():
    from massgen.mcp_tools.security import _get_default_allowed_executables

    for level in ("strict", "moderate", "permissive"):
        assert "srt" in _get_default_allowed_executables(level)


def test_srt_wrapped_fs_tools_config_passes_mcp_security(srt_fs_manager):
    from massgen.mcp_tools.security import validate_server_security

    config = srt_fs_manager.get_workspace_tools_mcp_config()
    assert config["command"] == "srt"
    validate_server_security(config)  # must NOT raise


# --------------------------------------------------------------------------- #
# npx/npm launchers can't be srt-wrapped (registry + ~/.npm cache writes are
# blocked by the sandbox → E403/EPERM). They must be SKIPPED (keep app-layer
# protection), while non-network launchers (python3/fastmcp/global binary) wrap.
# --------------------------------------------------------------------------- #
def test_wrap_skips_npx_launcher(srt_fs_manager):
    npx_cfg = {
        "name": "filesystem",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/ws"],
    }
    out = srt_fs_manager._wrap_stdio_config_with_srt(dict(npx_cfg))
    assert out["command"] == "npx"  # unchanged — not wrapped


def test_wrap_applies_to_non_network_launcher(srt_fs_manager):
    # A plain python3/fastmcp launcher with no npx dependency IS wrapped.
    py_cfg = {
        "name": "filesystem",
        "type": "stdio",
        "command": "python3",
        "args": ["/path/my_server.py", "/ws"],
    }
    out = srt_fs_manager._wrap_stdio_config_with_srt(dict(py_cfg))
    assert out["command"] == "srt"
    assert out["args"][2:4] == ["sh", "-c"]
    assert out["args"][4].startswith("python3 ")


def test_wrap_skips_no_roots_wrapper(srt_fs_manager):
    # The no-roots wrapper runs as python3 but INTERNALLY spawns npx → must be skipped.
    cfg = {
        "name": "filesystem",
        "type": "stdio",
        "command": "python3",
        "args": ["/abs/massgen/mcp_tools/filesystem_no_roots.py", "/ws"],
    }
    out = srt_fs_manager._wrap_stdio_config_with_srt(dict(cfg))
    assert out["command"] == "python3"  # unchanged — not wrapped


def test_wrap_skips_absolute_path_npx(srt_fs_manager):
    # A token-based skip must catch an absolute-path npx (not just bare "npx").
    cfg = {"name": "filesystem", "type": "stdio", "command": "/usr/local/bin/npx", "args": ["server"]}
    out = srt_fs_manager._wrap_stdio_config_with_srt(dict(cfg))
    assert out["command"] == "/usr/local/bin/npx"  # unchanged — not wrapped
