"""Native-sandbox backends must degrade `command_line_execution_mode: srt` to local.

Codex/claude_code self-sandbox (codex `--full-auto` = Landlock/Seatbelt). Wrapping
their MCP command execution in `srt` (another Seatbelt) nests sandboxes and hangs —
proven by a live smoke test where codex+srt timed out but codex+local succeeded.
SRT is only for backends WITHOUT a native execution sandbox.
"""

from massgen.backend.base import FilesystemSupport, LLMBackend


class _StubBackend(LLMBackend):
    """Minimal concrete backend (MCP filesystem support) for testing the degrade."""

    _native_sandbox = False

    async def stream_with_tools(self, messages, tools, **kwargs):  # pragma: no cover
        if False:
            yield

    def get_provider_name(self) -> str:
        return "stub"

    def get_filesystem_support(self) -> FilesystemSupport:
        return FilesystemSupport.MCP

    def has_native_execution_sandbox(self) -> bool:
        return self._native_sandbox


def test_api_backend_without_native_sandbox_keeps_srt(tmp_path):
    b = _StubBackend(cwd=str(tmp_path / "ws"), enable_mcp_command_line=True, command_line_execution_mode="srt")
    assert b.filesystem_manager.command_line_execution_mode == "srt"


def test_native_sandbox_backend_degrades_srt_to_local(tmp_path):
    class _NativeStub(_StubBackend):
        _native_sandbox = True

    b = _NativeStub(cwd=str(tmp_path / "ws2"), enable_mcp_command_line=True, command_line_execution_mode="srt")
    assert b.filesystem_manager.command_line_execution_mode == "local"


def test_degrade_does_not_touch_docker_or_local(tmp_path):
    class _NativeStub(_StubBackend):
        _native_sandbox = True

    b = _NativeStub(cwd=str(tmp_path / "ws3"), enable_mcp_command_line=True, command_line_execution_mode="local")
    assert b.filesystem_manager.command_line_execution_mode == "local"


def test_base_default_has_no_native_execution_sandbox(tmp_path):
    b = _StubBackend(cwd=str(tmp_path / "ws4"), enable_mcp_command_line=True, command_line_execution_mode="local")
    assert b.has_native_execution_sandbox() is False


def test_codex_and_claude_code_declare_native_sandbox():
    from massgen.backend.claude_code import ClaudeCodeBackend
    from massgen.backend.codex import CodexBackend

    # Method returns a constant; call it on an uninitialized instance to avoid
    # heavy backend construction (CLI/auth/etc).
    assert CodexBackend.has_native_execution_sandbox(object.__new__(CodexBackend)) is True
    assert ClaudeCodeBackend.has_native_execution_sandbox(object.__new__(ClaudeCodeBackend)) is True
