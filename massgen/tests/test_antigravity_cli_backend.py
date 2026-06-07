"""Tests for Antigravity CLI backend.

The Antigravity CLI (`agy`, Google's successor to the Gemini CLI as of I/O 2026)
is architecturally simpler than the Gemini CLI: plain text stdout, no
stream-json events. (agy 1.0.5+ does have a real --model flag, resolved from
the configured model id.) These tests pin the contract MassGen depends on.

Run with: uv run pytest massgen/tests/test_antigravity_cli_backend.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from massgen.backend.antigravity_cli import (
    AGY_DEFAULT_MODEL_LABEL,
    AntigravityCLIBackend,
)


@pytest.fixture
def backend(tmp_path):
    """AntigravityCLIBackend with binary mocked and cwd in a temp dir.

    Uses ``skip_health_check=True`` so we don't try to subprocess-invoke the
    fake binary path — health-check coverage lives in TestBinaryHealthCheck.
    """
    with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/bin/agy"):
        return AntigravityCLIBackend(cwd=str(tmp_path), skip_health_check=True)


class TestBinaryDiscovery:
    """The backend must locate the `agy` binary; refuse to construct otherwise."""

    def test_find_agy_cli_returns_path_on_path(self, tmp_path):
        fake_bin = tmp_path / "agy"
        fake_bin.write_text("")
        fake_bin.chmod(0o755)
        with patch("shutil.which", return_value=str(fake_bin)):
            assert AntigravityCLIBackend._find_agy_cli() == str(fake_bin)

    def test_find_agy_cli_returns_local_bin_fallback(self, monkeypatch, tmp_path):
        # No `agy` on PATH, but installer-default location exists
        with patch("shutil.which", return_value=None):
            home = tmp_path
            agy_path = home / ".local" / "bin" / "agy"
            agy_path.parent.mkdir(parents=True)
            agy_path.write_text("")
            agy_path.chmod(0o755)
            monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
            assert AntigravityCLIBackend._find_agy_cli() == str(agy_path)

    def test_construct_raises_when_binary_missing(self):
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value=None):
            with pytest.raises(RuntimeError, match="install.sh"):
                AntigravityCLIBackend()


class TestBinaryHealthCheck:
    """At construction, the backend must verify `agy --version` actually runs.

    This catches stale/corrupt installs (binary file exists but doesn't execute)
    BEFORE the orchestrator burns a coordination round on it.
    """

    def test_construction_runs_version_subprocess(self, tmp_path):
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/bin/agy"):
            with patch("subprocess.run") as run_mock:
                run_mock.return_value.returncode = 0
                run_mock.return_value.stdout = "1.0.0\n"
                run_mock.return_value.stderr = ""
                AntigravityCLIBackend(cwd=str(tmp_path))
                assert run_mock.called
                args = run_mock.call_args[0][0]
                assert args[0] == "/fake/bin/agy"
                assert "--version" in args

    def test_construction_raises_clear_error_on_nonzero_exit(self, tmp_path):
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/bin/agy"):
            with patch("subprocess.run") as run_mock:
                run_mock.return_value.returncode = 127
                run_mock.return_value.stdout = ""
                run_mock.return_value.stderr = "agy: ELF load failure"
                with pytest.raises(RuntimeError, match="exited with code 127"):
                    AntigravityCLIBackend(cwd=str(tmp_path))

    def test_construction_raises_clear_error_on_timeout(self, tmp_path):
        import subprocess

        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/bin/agy"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=5)):
                with pytest.raises(RuntimeError, match="won't run"):
                    AntigravityCLIBackend(cwd=str(tmp_path))

    def test_skip_health_check_bypasses_subprocess(self, tmp_path):
        # Escape hatch for tests / unusual environments.
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/bin/agy"):
            with patch("subprocess.run") as run_mock:
                AntigravityCLIBackend(cwd=str(tmp_path), skip_health_check=True)
                assert not run_mock.called


class TestCommandConstruction:
    """The backend invokes `agy` with the right flags for our use cases."""

    def test_minimal_command_uses_print_mode_with_yolo(self, backend):
        cmd = backend._build_exec_command("hello")
        assert cmd[0] == "/fake/bin/agy"
        # -p drives non-interactive mode; the prompt comes after the flag
        assert "-p" in cmd
        # `--dangerously-skip-permissions` is the agy equivalent of `--approval-mode yolo`
        assert "--dangerously-skip-permissions" in cmd
        # The user prompt must end up as a real arg, not interpolated
        assert "hello" in cmd

    def test_command_never_emits_conversation_or_continue_flags(self, backend):
        # Each MassGen call is a single-shot `-p` invocation; the orchestrator
        # already replays prior-response context in retry prompts, so agy-side
        # session resumption is unnecessary (and `--conversation` with a UUID
        # we generated fails with "conversation X not found" since agy assigns
        # its own IDs). The backend must never emit these flags.
        cmd = backend._build_exec_command("again")
        assert "--conversation" not in cmd
        assert "--continue" not in cmd
        assert "-c" not in cmd

    def test_command_passes_gemini_dir_for_workspace_isolation(self, backend, tmp_path):
        # agy honors a hidden `--gemini_dir <abs_path>` flag (verified via binary
        # strings + live test). We use it so each session gets an isolated config
        # root and never mutates the user's ~/.gemini/.
        backend._config_cwd = str(tmp_path / "cwd")
        cmd = backend._build_exec_command("hello")
        assert any(arg.startswith("--gemini_dir") for arg in cmd), f"--gemini_dir flag missing from: {cmd}"
        # Path arg must be absolute (agy logs reject relative: ".gemini must be an absolute path")
        gd_index = next(i for i, a in enumerate(cmd) if a == "--gemini_dir" or a.startswith("--gemini_dir="))
        if cmd[gd_index] == "--gemini_dir":
            path_arg = cmd[gd_index + 1]
        else:
            path_arg = cmd[gd_index].split("=", 1)[1]
        assert Path(path_arg).is_absolute(), f"--gemini_dir path must be absolute, got {path_arg!r}"
        assert ".antigravity" in path_arg

    def test_command_passes_add_dir_for_workspace_registration(self, backend, tmp_path):
        # Without --add-dir, agy writes files to .antigravity/antigravity-cli/
        # scratch/, hiding them from peers + snapshot promotion. We must pass
        # --add-dir <cwd> so write_to_file/view_file act on the workspace root.
        cmd = backend._build_exec_command("hello")
        assert "--add-dir" in cmd, f"--add-dir flag missing from: {cmd}"
        idx = cmd.index("--add-dir")
        path_arg = cmd[idx + 1]
        assert Path(path_arg).is_absolute(), f"--add-dir path must be absolute, got {path_arg!r}"
        # Must match the workspace cwd, NOT a subdir like .antigravity/ — that
        # would defeat the purpose (agy would still write outside the workspace).
        assert ".antigravity" not in path_arg, f"--add-dir must target workspace root, not config dir: {path_arg}"
        # And it must equal the backend's reported cwd (resolved).
        assert path_arg == str(Path(backend.cwd).resolve())

    def test_command_passes_log_file_for_error_surfacing(self, backend, tmp_path):
        # agy exits 0 with empty stdout on quota/auth failures. We capture
        # `--log-file` so silent failures can be surfaced as real errors.
        backend._config_cwd = str(tmp_path / "cwd")
        cmd = backend._build_exec_command("hello")
        assert "--log-file" in cmd, f"--log-file flag missing from: {cmd}"
        idx = cmd.index("--log-file")
        log_path = cmd[idx + 1]
        assert Path(log_path).is_absolute()
        assert ".antigravity" in log_path

    def test_command_passes_model_flag_for_known_alias(self, backend):
        """agy 1.0.5+ has a real --model flag taking an exact `agy models` label.

        A configured short id (e.g. ``gemini-3.5-flash``) must resolve to the
        canonical agy label and be emitted as ``--model <label>``.
        """
        backend.model = "gemini-3.5-flash"
        cmd = backend._build_exec_command("hello")
        assert "--model" in cmd, f"--model flag missing from: {cmd}"
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "Gemini 3.5 Flash (High)", cmd

    def test_command_passes_model_flag_for_exact_label(self, backend):
        """An already-canonical label is emitted verbatim (case-insensitive match)."""
        backend.model = "Gemini 3.1 Pro (High)"
        cmd = backend._build_exec_command("hello")
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "Gemini 3.1 Pro (High)"

    def test_command_omits_model_flag_for_unresolvable_model(self, backend):
        """An unrecognizable model id must NOT be passed (agy would reject it).

        Falling back to agy's default is safer than emitting a bad --model that
        makes the whole call fail.
        """
        backend.model = "totally-unknown-model-xyz"
        cmd = backend._build_exec_command("hello")
        assert "--model" not in cmd


class TestModelResolution:
    """Configured model ids map to exact `agy models` labels for --model."""

    @pytest.mark.parametrize(
        "configured,expected",
        [
            ("gemini-3.5-flash", "Gemini 3.5 Flash (High)"),
            ("gemini-3.5-flash-low", "Gemini 3.5 Flash (Low)"),
            ("gemini-3.5-flash-medium", "Gemini 3.5 Flash (Medium)"),
            ("gemini-3.1-pro", "Gemini 3.1 Pro (High)"),
            ("gemini-3.1-pro-low", "Gemini 3.1 Pro (Low)"),
            ("claude-sonnet-4.6", "Claude Sonnet 4.6 (Thinking)"),
            ("claude-opus-4.6", "Claude Opus 4.6 (Thinking)"),
            ("gpt-oss-120b", "GPT-OSS 120B (Medium)"),
            # Exact labels pass through (case-insensitive)
            ("Gemini 3.5 Flash (High)", "Gemini 3.5 Flash (High)"),
            ("gemini 3.5 flash (medium)", "Gemini 3.5 Flash (Medium)"),
            # Default label resolves to itself
            (AGY_DEFAULT_MODEL_LABEL, "Gemini 3.5 Flash (High)"),
        ],
    )
    def test_resolve_known_models(self, configured, expected):
        assert AntigravityCLIBackend._resolve_agy_model_label(configured) == expected

    @pytest.mark.parametrize("bad", ["", None, "gpt-4o", "llama-3", "random"])
    def test_resolve_unknown_returns_none(self, bad):
        assert AntigravityCLIBackend._resolve_agy_model_label(bad) is None


class TestScratchPromotion:
    """agy may route write_to_file into its internal scratch dir (excluded from
    snapshots). After each run we promote new scratch files into the workspace
    root so deliverables stay visible — without clobbering files the model
    already placed in the workspace."""

    def _scratch_dir(self, backend):
        return backend._workspace_config_dir() / "antigravity-cli" / "scratch"

    def test_promote_copies_new_scratch_file_to_workspace(self, backend):
        scratch = self._scratch_dir(backend)
        scratch.mkdir(parents=True, exist_ok=True)
        pre = backend._snapshot_scratch_files(scratch)
        deliverable = scratch / "result.svg"
        deliverable.write_text("<svg/>")
        promoted = backend._promote_scratch_deliverables(pre)
        assert "result.svg" in promoted
        dest = Path(backend.cwd).resolve() / "result.svg"
        assert dest.exists() and dest.read_text() == "<svg/>"

    def test_promote_preserves_subdir_structure(self, backend):
        scratch = self._scratch_dir(backend)
        (scratch / "out").mkdir(parents=True, exist_ok=True)
        pre = backend._snapshot_scratch_files(scratch)
        (scratch / "out" / "a.txt").write_text("x")
        promoted = backend._promote_scratch_deliverables(pre)
        assert any(p.replace("\\", "/") == "out/a.txt" for p in promoted)
        assert (Path(backend.cwd).resolve() / "out" / "a.txt").read_text() == "x"

    def test_promote_does_not_clobber_existing_workspace_file(self, backend):
        scratch = self._scratch_dir(backend)
        scratch.mkdir(parents=True, exist_ok=True)
        pre = backend._snapshot_scratch_files(scratch)
        (scratch / "result.svg").write_text("FROM_SCRATCH")
        ws_file = Path(backend.cwd).resolve() / "result.svg"
        ws_file.write_text("MODEL_PLACED")
        promoted = backend._promote_scratch_deliverables(pre)
        assert "result.svg" not in promoted
        assert ws_file.read_text() == "MODEL_PLACED"

    def test_promote_ignores_preexisting_scratch_files(self, backend):
        scratch = self._scratch_dir(backend)
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "old.txt").write_text("old")
        pre = backend._snapshot_scratch_files(scratch)
        promoted = backend._promote_scratch_deliverables(pre)
        assert promoted == []
        assert not (Path(backend.cwd).resolve() / "old.txt").exists()

    def test_promote_noop_when_scratch_missing(self, backend):
        # No scratch dir at all → empty result, no crash.
        assert backend._promote_scratch_deliverables({}) == []


class TestMCPConfigEmission:
    """MCP server entries must use Antigravity's schema (serverUrl, not url)."""

    def test_http_server_emits_serverUrl_not_url(self, backend):
        backend.mcp_servers = [
            {
                "name": "remote_thing",
                "url": "https://api.example.com/mcp/",
                "headers": {"Authorization": "Bearer X"},
            },
        ]
        cfg = backend._build_mcp_config_dict()
        assert "remote_thing" in cfg
        entry = cfg["remote_thing"]
        assert entry.get("serverUrl") == "https://api.example.com/mcp/"
        assert "url" not in entry
        assert entry.get("headers") == {"Authorization": "Bearer X"}

    def test_stdio_server_emits_command_args_env(self, backend):
        backend.mcp_servers = [
            {
                "name": "local_thing",
                "command": "node",
                "args": ["/path/to/server.js"],
                "env": {"FOO": "bar"},
            },
        ]
        cfg = backend._build_mcp_config_dict()
        entry = cfg["local_thing"]
        assert entry["command"] == "node"
        assert entry["args"] == ["/path/to/server.js"]
        assert entry["env"] == {"FOO": "bar"}
        assert "serverUrl" not in entry

    def test_servers_passed_as_dict_map_are_accepted(self, backend):
        """Some config schemas pass mcp_servers as a name-keyed dict, not a list."""
        backend.config["mcp_servers"] = {
            "alpha": {"command": "alpha-bin"},
            "beta": {"url": "https://beta.example.com/"},
        }
        cfg = backend._build_mcp_config_dict()
        assert cfg["alpha"]["command"] == "alpha-bin"
        assert cfg["beta"]["serverUrl"] == "https://beta.example.com/"
        assert "url" not in cfg["beta"]

    def test_empty_servers_returns_empty_dict(self, backend):
        backend.mcp_servers = []
        cfg = backend._build_mcp_config_dict()
        assert cfg == {}


class TestMCPConfigFile:
    """The backend writes mcp_config.json to a workspace-local `.antigravity/config/` dir
    that agy reads via `--gemini_dir`. The user's global ~/.gemini/ is never touched."""

    def test_write_mcp_config_writes_to_workspace_gemini_dir(self, tmp_path):
        # No monkeypatching needed — the path is derived from cwd, not a module global.
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/agy"):
            be = AntigravityCLIBackend(cwd=str(tmp_path / "cwd"), skip_health_check=True)
            be.mcp_servers = [{"name": "only_one", "command": "/x"}]
            be._write_mcp_config()

            expected = be._workspace_config_dir() / "config" / "mcp_config.json"
            assert expected.exists(), f"expected workspace-local mcp_config at {expected}"
            written = json.loads(expected.read_text())
            assert "only_one" in written["mcpServers"]

    def test_write_mcp_config_does_not_touch_user_global_file(self, tmp_path, monkeypatch):
        # Sentinel: place a marker at the *old* user-global path; assert it's untouched.
        # We do this by pointing AGY_MCP_CONFIG_PATH at a tmp file we control.
        sentinel = tmp_path / "sentinel_global_mcp.json"
        sentinel.write_text('{"mcpServers": {"user_only": {"command": "/u"}}}')
        monkeypatch.setattr(
            "massgen.backend.antigravity_cli.AGY_MCP_CONFIG_PATH",
            sentinel,
        )
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/agy"):
            be = AntigravityCLIBackend(cwd=str(tmp_path / "cwd"), skip_health_check=True)
            be.mcp_servers = [{"name": "mine", "command": "/m"}]
            be._write_mcp_config()
            be._restore_mcp_config()

            after = json.loads(sentinel.read_text())
            assert after == {"mcpServers": {"user_only": {"command": "/u"}}}, "user-global mcp_config.json must remain untouched"

    def test_default_mcp_path_constant_preserved_for_compat(self):
        # The module-level constant still exists for backward compat / introspection
        # but is no longer the active write target.
        from massgen.backend.antigravity_cli import AGY_MCP_CONFIG_PATH

        assert AGY_MCP_CONFIG_PATH == Path.home() / ".gemini" / "config" / "mcp_config.json"

    def test_workspace_mcp_path_is_isolated_per_cwd(self, tmp_path):
        """Each backend instance writes to its own cwd-scoped mcp_config.json."""
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/agy"):
            be_a = AntigravityCLIBackend(cwd=str(tmp_path / "a"), skip_health_check=True)
            be_b = AntigravityCLIBackend(cwd=str(tmp_path / "b"), skip_health_check=True)
            assert be_a._workspace_mcp_config_path() != be_b._workspace_mcp_config_path()
            for be in (be_a, be_b):
                assert be._workspace_mcp_config_path().is_absolute()


class TestAgentIdNotCollidingWithGeminiCli:
    """Custom-tools wiring must use the antigravity_cli identifier so coordination
    across mixed-backend runs (gemini_cli + antigravity_cli) stays distinguishable."""

    def test_agent_id_for_custom_tools_is_antigravity_cli(self, backend):
        # Probe via the module-level constant the implementation should expose
        from massgen.backend.antigravity_cli import AGY_AGENT_ID_LITERAL

        assert AGY_AGENT_ID_LITERAL == "antigravity_cli"


class TestProviderMetadata:
    """Backend identity surfaces correctly to the orchestrator."""

    def test_provider_name(self, backend):
        assert backend.get_provider_name() == "Antigravity CLI"

    def test_filesystem_support_is_native(self, backend):
        from massgen.backend.base import FilesystemSupport

        assert backend.get_filesystem_support() == FilesystemSupport.NATIVE

    def test_default_model_label_is_gemini_3_flash(self):
        # agy server-selects the model; we expose a label only for UI/logging.
        assert "flash" in AGY_DEFAULT_MODEL_LABEL.lower()


class TestStdoutStreamingParser:
    """Plain-text stdout lines become content chunks; clean exit yields done."""

    @pytest.mark.asyncio
    async def test_stdout_lines_yield_content_chunks(self, backend):
        from massgen.backend.base import StreamChunk

        proc_mock = AsyncMock()

        async def _aiter_stdout():
            for line in (b"hello\n", b"world\n"):
                yield line

        proc_mock.stdout = _aiter_stdout()
        proc_mock.wait = AsyncMock(return_value=0)
        proc_mock.returncode = 0

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc_mock)):
            chunks = []
            async for chunk in backend._stream_local("hi"):
                chunks.append(chunk)

        contents = [c for c in chunks if c.type == "content"]
        done = [c for c in chunks if c.type == "done"]
        assert any("hello" in (c.content or "") for c in contents)
        assert any("world" in (c.content or "") for c in contents)
        assert len(done) == 1
        assert isinstance(done[0], StreamChunk)

    @pytest.mark.asyncio
    async def test_nonzero_exit_yields_error_chunk(self, backend):
        proc_mock = AsyncMock()

        async def _aiter_stdout():
            yield b"some warning text\n"

        proc_mock.stdout = _aiter_stdout()
        proc_mock.wait = AsyncMock(return_value=2)
        proc_mock.returncode = 2

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc_mock)):
            chunks = []
            async for chunk in backend._stream_local("hi"):
                chunks.append(chunk)

        errors = [c for c in chunks if c.type == "error"]
        assert len(errors) == 1
        assert "agy" in (errors[0].error or "").lower() or "exit" in (errors[0].error or "").lower()

    @pytest.mark.asyncio
    async def test_silent_quota_failure_is_surfaced_from_log_file(self, backend, tmp_path):
        # agy exits 0 with empty stdout on RESOURCE_EXHAUSTED. The backend
        # must scan the --log-file we pass and surface the real error so the
        # orchestrator stops retry-looping against an empty response.
        backend._config_cwd = str(tmp_path / "cwd")
        log_path = backend._agy_log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "I0520 09:23:29 server.go:1072 Sending user message\n" "E0520 09:23:30 log.go:398] agent executor error: RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 3h0m45s.\n",
            encoding="utf-8",
        )

        proc_mock = AsyncMock()

        async def _aiter_stdout():
            return
            yield  # pragma: no cover — empty generator

        proc_mock.stdout = _aiter_stdout()
        proc_mock.wait = AsyncMock(return_value=0)
        proc_mock.returncode = 0

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc_mock)):
            chunks = []
            async for chunk in backend._stream_local("hi"):
                chunks.append(chunk)

        errors = [c for c in chunks if c.type == "error"]
        contents = [c for c in chunks if c.type == "content"]
        assert errors, "silent agy failure must yield an error chunk"
        assert any("quota" in (c.error or "").lower() or "429" in (c.error or "") for c in errors)
        # User-visible content chunk should also flag the failure so the TUI
        # shows what happened instead of an empty agent panel.
        assert any("Antigravity CLI ERROR" in (c.content or "") for c in contents)


class TestWorkspaceProjectMarker:
    """agy walks up from cwd looking for `.antigravitycli/` to identify its
    project root. Without an anchor at the workspace level, agy adopts
    whichever ancestor directory happens to contain one — making --add-dir
    ineffective and routing file writes to agy's internal scratch directory.
    """

    def test_project_marker_path_is_under_workspace_cwd(self, backend, tmp_path):
        marker = backend._workspace_project_marker_dir()
        assert marker.name == ".antigravitycli"
        # Must be in the workspace ROOT, not inside .antigravity/
        assert marker.parent == Path(backend.cwd).resolve()

    def test_ensure_creates_empty_marker_dir_when_missing(self, backend, tmp_path):
        marker = backend._workspace_project_marker_dir()
        assert not marker.exists()
        backend._ensure_workspace_project_marker()
        assert marker.exists() and marker.is_dir()

    def test_ensure_is_idempotent_when_marker_already_exists(self, backend, tmp_path):
        marker = backend._workspace_project_marker_dir()
        marker.mkdir(parents=True, exist_ok=True)
        # Add a sentinel file so we can detect destructive recreation.
        (marker / "sentinel.json").write_text("preserve me")
        backend._ensure_workspace_project_marker()
        assert (marker / "sentinel.json").exists()
        assert (marker / "sentinel.json").read_text() == "preserve me"

    def test_ensure_does_not_raise_on_oserror(self, backend, tmp_path, monkeypatch):
        # Simulate a filesystem error — the warning is logged but we must
        # not abort the backend startup over a non-fatal anchor failure.
        def _boom(*a, **kw):
            raise OSError("simulated")

        monkeypatch.setattr(Path, "mkdir", _boom)
        # Must not raise.
        backend._ensure_workspace_project_marker()


class TestHooksJsonWiring:
    """agy reads hooks from a standalone hooks.json (NOT embedded in
    settings.json like gemini_cli) and only when ``enableJsonHooks: true``
    is set in settings.json. Verified via binary-strings probe + live test.
    """

    def test_hooks_json_path_lives_in_workspace_config_dir(self, backend, tmp_path):
        path = backend._workspace_hooks_json_path()
        assert path.name == "hooks.json"
        # Must be under .antigravity/ so --gemini_dir points agy at it.
        assert ".antigravity" in str(path)

    def test_write_hooks_json_returns_false_when_no_hooks(self, backend, tmp_path):
        backend._config_cwd = str(tmp_path)
        backend._massgen_hooks_config = None
        assert backend._write_hooks_json() is False
        assert not backend._workspace_hooks_json_path().exists()

    def test_write_hooks_json_returns_false_for_empty_hooks_payload(self, backend, tmp_path):
        backend._config_cwd = str(tmp_path)
        backend._massgen_hooks_config = {"hooks": {}}
        assert backend._write_hooks_json() is False

    def test_write_hooks_json_emits_file_when_hooks_present(self, backend, tmp_path):
        backend._config_cwd = str(tmp_path)
        backend._massgen_hooks_config = {
            "hooks": {
                "BeforeTool": [{"matcher": ".*", "hooks": [{"type": "command", "command": "echo x"}]}],
            },
        }
        assert backend._write_hooks_json() is True
        path = backend._workspace_hooks_json_path()
        assert path.exists()
        written = json.loads(path.read_text())
        # Outer "hooks" key is required by agy's proto field tag
        # (`Hooks json:"hooks"` in the binary).
        assert "hooks" in written
        assert "BeforeTool" in written["hooks"]

    def test_settings_json_enables_json_hooks_flag_when_hooks_written(self, backend, tmp_path):
        backend._config_cwd = str(tmp_path)
        backend._write_workspace_settings_json(has_hooks=True)
        settings_path = backend._workspace_config_dir() / "settings.json"
        settings = json.loads(settings_path.read_text())
        # The `json-hooks-enabled` feature flag in agy binary is read from
        # this settings key; without it agy logs "skipping hooks.json".
        assert settings.get("enableJsonHooks") is True

    def test_settings_json_omits_flag_when_no_hooks(self, backend, tmp_path):
        backend._config_cwd = str(tmp_path)
        backend._write_workspace_settings_json(has_hooks=False)
        settings_path = backend._workspace_config_dir() / "settings.json"
        settings = json.loads(settings_path.read_text())
        # Don't set the flag if we have nothing to gate — leaves the user's
        # global default in place (and avoids the appearance of hooks being
        # configured when they aren't).
        assert "enableJsonHooks" not in settings

    def test_restore_removes_managed_hooks_json(self, backend, tmp_path):
        backend._config_cwd = str(tmp_path)
        backend._massgen_hooks_config = {
            "hooks": {"BeforeTool": [{"matcher": ".*", "hooks": [{"type": "command", "command": "x"}]}]},
        }
        backend._write_hooks_json()
        assert backend._workspace_hooks_json_path().exists()
        backend._restore_hooks_json()
        assert not backend._workspace_hooks_json_path().exists()

    def test_write_sets_adapter_hook_dir_to_workspace_config_dir(self, backend, tmp_path):
        # Mirrors gemini_cli.py:1163-1164 — the adapter needs a hook_dir so
        # `build_native_hooks_config` knows where IPC payload files live.
        backend._config_cwd = str(tmp_path)
        backend._massgen_hooks_config = {
            "hooks": {"BeforeTool": [{"matcher": ".*", "hooks": [{"type": "command", "command": "x"}]}]},
        }
        backend._write_hooks_json()
        adapter = getattr(backend, "_native_hook_adapter", None)
        assert adapter is not None
        if hasattr(adapter, "hook_dir"):
            assert adapter.hook_dir == backend._workspace_config_dir()


class TestNativeHookDirWiringRound1:
    """Regression for the round-1 native-hook gap.

    The orchestrator builds the native hooks config by calling
    ``get_native_hook_adapter()`` and then ``adapter.build_native_hooks_config()``
    BEFORE the backend's stream ever runs ``_write_hooks_json`` (which is where
    ``hook_dir`` used to be set lazily). On the very first round the adapter's
    ``hook_dir`` was therefore ``None``, so ``build_native_hooks_config`` returned
    ``{}`` and the initial-answer round ran with NO MassGen native hooks.

    These tests drive the REAL build path — they do NOT pre-populate
    ``_massgen_hooks_config`` (which is what let the older TestHooksJsonWiring
    tests pass despite the bug).
    """

    def _manager_with_hooks(self):
        from massgen.mcp_tools.hooks import (
            GeneralHookManager,
            HookType,
            PythonCallableHook,
        )

        manager = GeneralHookManager()
        manager.register_global_hook(
            HookType.PRE_TOOL_USE,
            PythonCallableHook(name="t_pre", handler=lambda _e: None, matcher="*"),
        )
        manager.register_global_hook(
            HookType.POST_TOOL_USE,
            PythonCallableHook(name="t_post", handler=lambda _e: None, matcher="*"),
        )
        return manager

    def test_get_native_hook_adapter_sets_hook_dir(self, backend):
        # The orchestrator fetches the adapter via this accessor right before
        # building the config. It must come back with hook_dir already set.
        adapter = backend.get_native_hook_adapter()
        assert adapter is not None
        assert adapter.hook_dir is not None, "hook_dir is None at orchestrator build time — round-1 hooks lost"
        assert Path(adapter.hook_dir) == backend._workspace_config_dir()

    def test_build_native_hooks_config_nonempty_on_first_round(self, backend):
        # Simulate exactly what the orchestrator does on round 1: fetch adapter,
        # then build. Must NOT return {} (the round-1 bug).
        manager = self._manager_with_hooks()
        adapter = backend.get_native_hook_adapter()
        cfg = adapter.build_native_hooks_config(manager, agent_id="agent_b")
        assert cfg.get("hooks"), f"round-1 build returned empty config: {cfg!r}"
        assert "BeforeTool" in cfg["hooks"]
        assert "AfterTool" in cfg["hooks"]

    def test_full_round1_flow_writes_hooks_json_and_enables_flag(self, backend):
        # End-to-end round-1 simulation: orchestrator builds + sets the config,
        # then the backend's stream-time _write_hooks_json must actually emit a
        # hooks.json and the enableJsonHooks gate.
        manager = self._manager_with_hooks()
        adapter = backend.get_native_hook_adapter()
        backend.set_native_hooks_config(adapter.build_native_hooks_config(manager, agent_id="agent_b"))
        wrote = backend._write_hooks_json()
        assert wrote is True, "round-1 _write_hooks_json wrote nothing — native hooks missing in initial round"
        backend._write_workspace_settings_json(has_hooks=wrote)
        hooks_path = backend._workspace_hooks_json_path()
        assert hooks_path.exists()
        settings = json.loads((backend._workspace_config_dir() / "settings.json").read_text())
        assert settings.get("enableJsonHooks") is True


class TestAgentsMdAtomicity:
    """AGENTS.md write/restore must survive interruptions cleanly."""

    def test_write_uses_temp_then_rename(self, backend, tmp_path, monkeypatch):
        backend._config_cwd = str(tmp_path)
        backend.system_prompt = "system prompt body"

        # Capture the order of write+replace operations to assert atomicity.
        seen: list[tuple[str, str]] = []
        real_write_text = Path.write_text
        real_replace = os.replace

        def tracking_write_text(self, *a, **kw):
            seen.append(("write_text", str(self)))
            return real_write_text(self, *a, **kw)

        def tracking_replace(src, dst):
            seen.append(("replace", f"{src}->{dst}"))
            return real_replace(src, dst)

        monkeypatch.setattr(Path, "write_text", tracking_write_text)
        monkeypatch.setattr(os, "replace", tracking_replace)

        backend._write_system_prompt_md()
        final_path = backend._workspace_agents_md_path()
        assert final_path.read_text() == "system prompt body"
        # The write must hit the temp file first, then be renamed onto target.
        write_op = next(op for op in seen if op[0] == "write_text")
        replace_op = next(op for op in seen if op[0] == "replace")
        assert ".massgen_tmp" in write_op[1], f"write_text should target temp file, got {write_op}"
        assert ".massgen_tmp" in replace_op[1] and "AGENTS.md" in replace_op[1]

    def test_restore_cleans_up_stale_temp_file(self, backend, tmp_path):
        # Simulate a previous call that crashed between write-to-temp and rename:
        # a `.massgen_tmp` file lingers but no AGENTS.md was ever published.
        backend._config_cwd = str(tmp_path)
        target = backend._workspace_agents_md_path()
        tmp_file = target.with_suffix(target.suffix + ".massgen_tmp")
        tmp_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file.write_text("partial write from a crashed run")

        backend._restore_system_prompt_md()
        assert not tmp_file.exists(), "stale .massgen_tmp must be cleaned up on restore"
        assert not target.exists(), "no original AGENTS.md should be created from temp leftovers"

    def test_restore_runs_even_if_backup_missing(self, backend, tmp_path):
        # Common case: no pre-existing AGENTS.md, we wrote one, we remove it.
        backend._config_cwd = str(tmp_path)
        target = backend._workspace_agents_md_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("managed content")

        backend._restore_system_prompt_md()
        assert not target.exists()

    def test_restore_preserves_user_owned_agents_md(self, backend, tmp_path):
        # User had their own AGENTS.md. We wrote ours over it (with a backup).
        # Restore must put theirs back, not leave ours behind.
        backend._config_cwd = str(tmp_path)
        backend.system_prompt = "MassGen-injected"
        target = backend._workspace_agents_md_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("USER OWNED CONTENT")

        backend._write_system_prompt_md()
        assert target.read_text() == "MassGen-injected"
        backend._restore_system_prompt_md()
        assert target.read_text() == "USER OWNED CONTENT"


class TestMultimodalContent:
    """Non-text message parts must be surfaced to agy as readable references
    (paths/URLs) rather than silently dropped — agy has filesystem/shell tools
    and can ``read`` an image path or fetch a URL when prompted.
    """

    def test_plain_text_passthrough(self, backend):
        assert backend._message_content_to_text("just text") == "just text"

    def test_text_parts_concatenate(self, backend):
        content = [
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "world"},
        ]
        assert backend._message_content_to_text(content) == "Hello world"

    def test_image_path_part_surfaces_as_reference(self, backend):
        content = [
            {"type": "text", "text": "Look at this: "},
            {"type": "image", "source_path": "/abs/path/photo.jpg"},
        ]
        out = backend._message_content_to_text(content)
        assert "Look at this:" in out
        assert "/abs/path/photo.jpg" in out
        # Must include a delimiter so the model can tell it's a reference
        assert "[" in out and "]" in out

    def test_image_url_part_surfaces_url(self, backend):
        content = [
            {"type": "image", "image_url": "https://example.com/x.jpg"},
        ]
        out = backend._message_content_to_text(content)
        assert "https://example.com/x.jpg" in out

    def test_audio_path_part_surfaces(self, backend):
        content = [{"type": "audio", "audio_path": "/clip.wav"}]
        assert "/clip.wav" in backend._message_content_to_text(content)

    def test_base64_inline_image_is_not_silently_dropped(self, backend):
        # We don't want to inline 100kb of base64 in the agy prompt, but we
        # also must not silently drop it. Surface a stub so the agent knows.
        content = [
            {"type": "image", "base64": "iVBORw0KGgo..." * 100, "mime_type": "image/png"},
        ]
        out = backend._message_content_to_text(content)
        assert out, "base64 image must produce SOME output, not empty string"
        assert "inline" in out.lower() or "base64" in out.lower() or "attachment" in out.lower()

    def test_unknown_typed_part_at_least_acknowledges_existence(self, backend):
        content = [{"type": "weird_custom_type"}]
        out = backend._message_content_to_text(content)
        assert "weird_custom_type" in out


class TestSubprocessCancellation:
    """When the orchestrator cancels the streaming generator, agy must die cleanly."""

    @pytest.mark.asyncio
    async def test_cancellation_terminates_agy_subprocess(self, backend):
        # Build a fake proc that's "still running" (returncode=None) until killed.
        proc_mock = AsyncMock()
        proc_mock.returncode = None
        terminate_called = {"value": False}
        kill_called = {"value": False}

        def _terminate():
            terminate_called["value"] = True
            proc_mock.returncode = 0  # simulate graceful exit after SIGTERM

        def _kill():
            kill_called["value"] = True
            proc_mock.returncode = -9

        proc_mock.terminate = _terminate
        proc_mock.kill = _kill
        proc_mock.wait = AsyncMock(return_value=0)

        async def _aiter_stdout():
            # Block forever so the consumer must cancel us
            await asyncio.sleep(60)
            return
            yield  # pragma: no cover

        proc_mock.stdout = _aiter_stdout()

        async def _consume():
            chunks = []
            async for chunk in backend._stream_local("hi"):
                chunks.append(chunk)
            return chunks

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc_mock)):
            task = asyncio.create_task(_consume())
            # Give the generator a moment to start the subprocess
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert terminate_called["value"], "agy subprocess must be SIGTERM'd on cancellation"
        # No SIGKILL needed because our fake terminate sets returncode=0 immediately
        assert not kill_called["value"]

    @pytest.mark.asyncio
    async def test_terminate_falls_back_to_kill_on_stubborn_subprocess(self, backend):
        # If SIGTERM doesn't elicit exit within grace, we must SIGKILL.
        proc_mock = AsyncMock()
        proc_mock.returncode = None
        proc_mock.terminate = lambda: None  # ignores SIGTERM

        kill_called = {"value": False}

        def _kill():
            kill_called["value"] = True
            proc_mock.returncode = -9

        proc_mock.kill = _kill
        proc_mock.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), 0])

        async def _waiter():
            raise TimeoutError()

        # Use very short grace so the test is fast.
        with patch("asyncio.wait_for", AsyncMock(side_effect=[asyncio.TimeoutError(), 0])):
            await backend._terminate_subprocess(proc_mock, grace_seconds=0.01)
        assert kill_called["value"], "must SIGKILL when SIGTERM grace expires"


class TestWorkflowModeInference:
    """Mirrors gemini_cli's workflow-mode trio — without these, agy ends up
    being told both `vote` and `new_answer` are valid in rounds where no
    candidate answers exist yet, which causes spurious vote calls and
    contributes to the over-submission behavior observed in v0.1.88 runs.
    """

    @staticmethod
    def _vote_and_new_answer_tools():
        return [
            {"type": "function", "function": {"name": "new_answer", "description": "..."}},
            {"type": "function", "function": {"name": "vote", "description": "..."}},
        ]

    def test_no_current_answers_block_returns_any(self, backend):
        # First-ever turn: no <CURRENT ANSWERS> block exists yet.
        messages = [{"role": "user", "content": "Build me something."}]
        mode = backend._infer_workflow_call_mode(messages, self._vote_and_new_answer_tools())
        assert mode == "any"

    def test_empty_current_answers_block_returns_new_answer_only(self, backend):
        # Block exists but contains no <agent…> tag → no one has answered yet.
        messages = [
            {
                "role": "user",
                "content": "<CURRENT ANSWERS from the agents>\n(no answers yet)\n<END OF CURRENT ANSWERS>",
            },
        ]
        mode = backend._infer_workflow_call_mode(messages, self._vote_and_new_answer_tools())
        assert mode == "new_answer_only"

    def test_populated_current_answers_block_returns_any(self, backend):
        messages = [
            {
                "role": "user",
                "content": "<CURRENT ANSWERS from the agents>\n<agent agent1>foo</agent>\n<END OF CURRENT ANSWERS>",
            },
        ]
        mode = backend._infer_workflow_call_mode(messages, self._vote_and_new_answer_tools())
        assert mode == "any"

    def test_filter_tools_drops_vote_in_new_answer_only(self, backend):
        tools = self._vote_and_new_answer_tools()
        filtered = backend._filter_workflow_tools_for_mode(tools, "new_answer_only")
        names = [t["function"]["name"] for t in filtered]
        assert "new_answer" in names
        assert "vote" not in names

    def test_filter_tools_no_op_in_any_mode(self, backend):
        tools = self._vote_and_new_answer_tools()
        filtered = backend._filter_workflow_tools_for_mode(tools, "any")
        assert {t["function"]["name"] for t in filtered} == {"new_answer", "vote"}

    def test_filter_parsed_calls_drops_vote_in_new_answer_only(self, backend):
        calls = [
            {"id": "x", "type": "function", "function": {"name": "vote", "arguments": {}}},
            {"id": "y", "type": "function", "function": {"name": "new_answer", "arguments": {}}},
        ]
        filtered = backend._filter_workflow_tool_calls_for_mode(calls, "new_answer_only")
        assert [c["function"]["name"] for c in filtered] == ["new_answer"]

    def test_new_answer_only_is_sticky_across_calls_with_no_block(self, backend):
        # Once we infer new_answer_only, a subsequent call with no block at all
        # should keep us there (mirrors gemini_cli's retry-sticky guard).
        msgs1 = [{"role": "user", "content": "<CURRENT ANSWERS from the agents>(empty)<END OF CURRENT ANSWERS>"}]
        assert backend._infer_workflow_call_mode(msgs1, self._vote_and_new_answer_tools()) == "new_answer_only"
        backend._workflow_call_mode = "new_answer_only"
        # Now no block — sticky should keep us in new_answer_only.
        msgs2 = [{"role": "user", "content": "Try again please."}]
        assert backend._infer_workflow_call_mode(msgs2, self._vote_and_new_answer_tools()) == "new_answer_only"

    def test_mode_inference_requires_both_vote_and_new_answer(self, backend):
        # If only `new_answer` is in tools, mode inference doesn't activate —
        # caller is in a non-coordination phase.
        tools = [{"type": "function", "function": {"name": "new_answer"}}]
        messages = [{"role": "user", "content": "<CURRENT ANSWERS from the agents>(empty)<END OF CURRENT ANSWERS>"}]
        assert backend._infer_workflow_call_mode(messages, tools) == "any"


class TestPhasePromptPrefix:
    """When the orchestrator hands us `submit` + `restart_orchestration`,
    we're in the post-evaluation phase. Mirror gemini_cli's behavior and
    prefix the prompt so agy doesn't follow stale `new_answer`/`vote`
    directives quoted in conversation history.
    """

    def test_post_eval_tools_emit_guard_prefix(self, backend):
        tools = [
            {"type": "function", "function": {"name": "submit"}},
            {"type": "function", "function": {"name": "restart_orchestration"}},
        ]
        prefix = backend._build_phase_prompt_prefix(tools)
        assert "POST-EVALUATION PHASE" in prefix
        assert "submit" in prefix and "restart_orchestration" in prefix

    def test_regular_workflow_tools_emit_no_prefix(self, backend):
        tools = [
            {"type": "function", "function": {"name": "vote"}},
            {"type": "function", "function": {"name": "new_answer"}},
        ]
        assert backend._build_phase_prompt_prefix(tools) == ""

    def test_partial_post_eval_tools_emit_no_prefix(self, backend):
        # Both must be present; one alone isn't post-eval.
        tools = [{"type": "function", "function": {"name": "submit"}}]
        assert backend._build_phase_prompt_prefix(tools) == ""


class TestAuthenticationPrecheck:
    """At stream time, the backend must refuse to launch agy if no
    credential source exists. Avoids burning a coordination round on a
    silent UNAUTHENTICATED 401 from the language server.
    """

    def test_has_creds_when_api_key_set(self, backend):
        backend.api_key = "test-key"
        assert backend._has_cached_credentials() is True

    def test_has_creds_when_google_accounts_json_exists(self, backend, tmp_path, monkeypatch):
        backend.api_key = None
        fake_home = tmp_path / "home"
        (fake_home / ".gemini").mkdir(parents=True)
        (fake_home / ".gemini" / "google_accounts.json").write_text("{}")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        assert backend._has_cached_credentials() is True

    def test_no_creds_returns_false(self, backend, tmp_path, monkeypatch):
        backend.api_key = None
        fake_home = tmp_path / "empty_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        assert backend._has_cached_credentials() is False

    @pytest.mark.asyncio
    async def test_stream_with_tools_yields_error_chunk_when_unauthenticated(self, backend, tmp_path, monkeypatch):
        backend.api_key = None
        fake_home = tmp_path / "empty_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        chunks = []
        async for chunk in backend.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        ):
            chunks.append(chunk)
        errors = [c for c in chunks if c.type == "error"]
        assert errors, "must yield an error chunk when not authenticated"
        assert "not authenticated" in (errors[0].error or "").lower() or "GEMINI_API_KEY" in (errors[0].error or "")


class TestAgentIdRefreshFromKwargs:
    """Parity with sibling backends — pick up agent_id from kwargs so the
    transcript emitter labels events for the right agent across calls.
    """

    @pytest.mark.asyncio
    async def test_agent_id_picked_up_from_kwargs(self, backend, tmp_path, monkeypatch):
        from massgen.backend.base import StreamChunk

        # Make auth check pass so we can exercise the agent_id assignment.
        backend.api_key = "x"
        backend.agent_id = None
        # Stub _stream_local to skip subprocess and just yield a done chunk.

        async def _stub_stream(prompt):
            yield StreamChunk(type="done", usage={})

        monkeypatch.setattr(backend, "_stream_local", _stub_stream)

        chunks = []
        async for chunk in backend.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            agent_id="agent_b",
        ):
            chunks.append(chunk)
        assert backend.agent_id == "agent_b"


class TestWorkflowToolTextFallback:
    """When MassGen orchestrator passes vote/new_answer tools, agy can't expose
    them as native MCP tools — agy 1.0.0 doesn't load MCP tools per invocation.
    The backend MUST inject formatting instructions into the prompt and parse
    the agent's text response for workflow tool calls."""

    @staticmethod
    def _workflow_tools():
        return [
            {
                "type": "function",
                "function": {
                    "name": "new_answer",
                    "description": "Submit a candidate answer.",
                    "parameters": {
                        "type": "object",
                        "properties": {"content": {"type": "string"}},
                        "required": ["content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "vote",
                    "description": "Vote for the best answer.",
                    "parameters": {
                        "type": "object",
                        "properties": {"agent_id": {"type": "string"}, "reason": {"type": "string"}},
                        "required": ["agent_id", "reason"],
                    },
                },
            },
        ]

    @pytest.mark.asyncio
    async def test_prompt_contains_workflow_instructions_when_workflow_tools_present(self, backend):
        """Workflow tool definitions must produce inline text-fallback instructions."""
        # Provide an api_key so the new _ensure_authenticated pre-check passes
        # without needing ~/.gemini/google_accounts.json on the CI runner.
        backend.api_key = "test-key"
        captured_cmd = {}
        proc_mock = AsyncMock()

        async def _aiter_stdout():
            for line in (b'{"tool_name": "new_answer", "arguments": {"content": "42"}}\n',):
                yield line

        proc_mock.stdout = _aiter_stdout()
        proc_mock.wait = AsyncMock(return_value=0)
        proc_mock.returncode = 0

        async def fake_exec(*args, **kwargs):
            captured_cmd["cmd"] = list(args)
            return proc_mock

        # The message must include a populated CURRENT ANSWERS block so
        # workflow-mode inference returns "any" — otherwise (no answers
        # block OR empty block), it returns "new_answer_only" and `vote`
        # is correctly stripped from the prompt, breaking the assertion.
        messages = [
            {
                "role": "user",
                "content": ("what is 2+2?\n\n" "<CURRENT ANSWERS from the agents>\n" "<agent agent1>placeholder answer</agent>\n" "<END OF CURRENT ANSWERS>"),
            },
        ]

        with patch("asyncio.create_subprocess_exec", new=fake_exec):
            chunks = []
            async for chunk in backend.stream_with_tools(
                messages=messages,
                tools=self._workflow_tools(),
            ):
                chunks.append(chunk)

        cmd = captured_cmd["cmd"]
        # The prompt is the LAST argument after `-p`. Inspect it.
        assert "-p" in cmd, f"missing -p flag in {cmd!r}"
        prompt_arg = cmd[cmd.index("-p") + 1]
        # The injection must teach the agent how to format workflow tool calls.
        # We don't pin the exact wording — just that it references the workflow
        # tools and the JSON structure the orchestrator parses.
        assert "new_answer" in prompt_arg, "workflow tool 'new_answer' not in prompt"
        assert "vote" in prompt_arg, "workflow tool 'vote' not in prompt"
        assert "tool_name" in prompt_arg, "JSON formatting hint missing from prompt"

    @pytest.mark.asyncio
    async def test_stdout_workflow_json_yields_tool_calls_chunk(self, backend):
        """When agy emits a workflow JSON envelope on stdout, the backend must
        emit a `StreamChunk(type="tool_calls")` so the orchestrator can act."""
        # auth pre-check needs a credential source.
        backend.api_key = "test-key"
        proc_mock = AsyncMock()

        async def _aiter_stdout():
            for line in (
                b"Here is my answer.\n",
                b'{"tool_name": "new_answer", "arguments": {"content": "42 is the answer"}}\n',
            ):
                yield line

        proc_mock.stdout = _aiter_stdout()
        proc_mock.wait = AsyncMock(return_value=0)
        proc_mock.returncode = 0

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc_mock)):
            chunks = []
            async for chunk in backend.stream_with_tools(
                messages=[{"role": "user", "content": "what is 2+2?"}],
                tools=self._workflow_tools(),
            ):
                chunks.append(chunk)

        tool_call_chunks = [c for c in chunks if c.type == "tool_calls"]
        assert len(tool_call_chunks) == 1, f"expected exactly one tool_calls chunk, got {[c.type for c in chunks]}"
        calls = tool_call_chunks[0].tool_calls or []
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "new_answer"
        assert calls[0]["function"]["arguments"].get("content") == "42 is the answer"

    @pytest.mark.asyncio
    async def test_no_workflow_tool_calls_chunk_when_no_workflow_tools_passed(self, backend):
        """If orchestrator doesn't request workflow tools, don't parse for them
        (avoids false-positive matches in arbitrary agent text)."""
        proc_mock = AsyncMock()

        async def _aiter_stdout():
            # This LOOKS like a workflow JSON but the orchestrator didn't request workflow tools.
            yield b'{"tool_name": "new_answer", "arguments": {"content": "spurious"}}\n'

        proc_mock.stdout = _aiter_stdout()
        proc_mock.wait = AsyncMock(return_value=0)
        proc_mock.returncode = 0

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc_mock)):
            chunks = []
            async for chunk in backend.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            ):
                chunks.append(chunk)

        tool_call_chunks = [c for c in chunks if c.type == "tool_calls"]
        assert tool_call_chunks == [], "must not parse workflow tool calls when no workflow tools are requested"


class TestDockerModeApiKeyAuth:
    """Docker mode requires API-key auth because agy's OAuth state isn't portable
    into a container. The backend writes a workspace-local settings.json that
    forces `selectedType: gemini-api-key`, and refuses to construct without a key."""

    def test_docker_mode_requires_api_key_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/agy"):
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY|GOOGLE_API_KEY|API.key"):
                AntigravityCLIBackend(
                    cwd=str(tmp_path / "cwd"),
                    command_line_execution_mode="docker",
                    skip_health_check=True,
                )

    def test_docker_mode_writes_api_key_settings_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "dummy-test-key")
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/agy"):
            be = AntigravityCLIBackend(
                cwd=str(tmp_path / "cwd"),
                command_line_execution_mode="docker",
                skip_health_check=True,
            )
            be._write_workspace_settings_json()
            settings_path = be._workspace_config_dir() / "settings.json"
            assert settings_path.exists()
            settings = json.loads(settings_path.read_text())
            assert settings.get("security", {}).get("auth", {}).get("selectedType") == "gemini-api-key"

    def test_local_mode_does_not_require_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        # Local mode uses OAuth from the host's ~/.gemini/google_accounts.json.
        with patch.object(AntigravityCLIBackend, "_find_agy_cli", return_value="/fake/agy"):
            AntigravityCLIBackend(cwd=str(tmp_path / "cwd"), skip_health_check=True)  # must not raise


class TestNativeHookAdapter:
    """agy 1.0.0 inherits Gemini CLI's hook framework (same exa.hooks_pb proto,
    same BeforeTool/AfterTool/Stop events). The backend exposes a thin
    AntigravityCLINativeHookAdapter so orchestrator code can register hooks
    just as it does for GeminiCLIBackend."""

    def test_backend_exposes_native_hook_adapter(self, backend):
        adapter = backend.get_native_hook_adapter()
        assert adapter is not None
        from massgen.mcp_tools.native_hook_adapters.antigravity_cli_adapter import (
            AntigravityCLINativeHookAdapter,
        )

        assert isinstance(adapter, AntigravityCLINativeHookAdapter)

    def test_adapter_inherits_gemini_cli_hook_behavior(self):
        from massgen.mcp_tools.native_hook_adapters.antigravity_cli_adapter import (
            AntigravityCLINativeHookAdapter,
        )
        from massgen.mcp_tools.native_hook_adapters.gemini_cli_adapter import (
            GeminiCLINativeHookAdapter,
        )

        assert issubclass(AntigravityCLINativeHookAdapter, GeminiCLINativeHookAdapter)


class TestSubprocessEnv:
    """Env passed to agy must include API keys (passthrough) and disable auto-update during tests."""

    def test_build_subprocess_env_passes_through_gemini_api_key(self, monkeypatch, backend):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-abc")
        env = backend._build_subprocess_env()
        assert env.get("GEMINI_API_KEY") == "test-key-abc"

    def test_build_subprocess_env_disables_auto_update_when_requested(self, backend):
        backend.disable_auto_update = True
        env = backend._build_subprocess_env()
        assert env.get("AGY_CLI_DISABLE_AUTO_UPDATE") == "1"


class TestMcpServerHookPayloads:
    """agy parity with codex for the MCP-middleware mid-stream injection IPC.

    The orchestrator's per-chunk flush is backend-agnostic (gated only on
    `write_post_tool_use_hook` + `supports_mcp_server_hooks()`), so these methods
    let agy participate in the same MCP-middleware injection path codex uses.
    (Live end-to-end delivery shares the unresolved Codex MCP-client gap — see
    test_codex_middleware_firing_live.py.)
    """

    def test_supports_mcp_server_hooks(self, backend):
        assert backend.supports_mcp_server_hooks() is True

    def test_hook_dir_is_workspace_config_dir(self, backend):
        assert backend.get_hook_dir() == backend._workspace_config_dir()

    def test_write_then_read_roundtrip(self, backend):
        backend.write_post_tool_use_hook("[Human Input]: steer agy")
        # File present until consumed
        assert (backend.get_hook_dir() / "hook_post_tool_use.json").exists()
        content = backend.read_unconsumed_hook_content()
        assert content == "[Human Input]: steer agy"
        # read consumes it
        assert not (backend.get_hook_dir() / "hook_post_tool_use.json").exists()
        assert backend.read_unconsumed_hook_content() is None

    def test_write_payload_shape_matches_middleware_contract(self, backend):
        backend.write_post_tool_use_hook("hi", tool_matcher="*")
        data = json.loads((backend.get_hook_dir() / "hook_post_tool_use.json").read_text())
        assert data["inject"]["content"] == "hi"
        assert data["inject"]["strategy"] == "tool_result"
        assert data["tool_matcher"] == "*"
        assert isinstance(data["expires_at"], float)
        assert data["sequence"] == 1

    def test_sequence_increments(self, backend):
        backend.write_post_tool_use_hook("a")
        backend.write_post_tool_use_hook("b")
        data = json.loads((backend.get_hook_dir() / "hook_post_tool_use.json").read_text())
        assert data["sequence"] == 2

    def test_clear_hook_files(self, backend):
        backend.write_post_tool_use_hook("x")
        backend.clear_hook_files()
        assert not (backend.get_hook_dir() / "hook_post_tool_use.json").exists()
