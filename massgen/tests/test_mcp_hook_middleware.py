"""Tests for MassGenHookMiddleware — FastMCP server-level PostToolUse injection."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_hook_file(hook_dir: Path, payload: dict) -> Path:
    """Write a hook_post_tool_use.json file."""
    hook_dir.mkdir(parents=True, exist_ok=True)
    path = hook_dir / "hook_post_tool_use.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_payload(
    content: str = "injected content",
    tool_matcher: str = "*",
    expires_at: float | None = None,
    sequence: int = 1,
) -> dict:
    return {
        "inject": {"content": content, "strategy": "tool_result"},
        "tool_matcher": tool_matcher,
        "expires_at": expires_at or (time.time() + 60),
        "sequence": sequence,
    }


# ---------------------------------------------------------------------------
# Unit tests for _read_post_tool_use_injection
# ---------------------------------------------------------------------------


class TestReadPostToolUseInjection:
    """Tests for the file-based IPC read logic."""

    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        assert mw._read_post_tool_use_injection("some_tool") is None

    def test_reads_and_returns_injection_content(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        payload = _make_payload(content="hello from peer")
        _write_hook_file(tmp_path, payload)

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        result = mw._read_post_tool_use_injection("any_tool")
        assert result == "hello from peer"

    def test_consumes_file_after_read(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload())

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        mw._read_post_tool_use_injection("any_tool")

        # File should be deleted
        assert not (tmp_path / "hook_post_tool_use.json").exists()

    def test_skips_expired_payload(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        payload = _make_payload(expires_at=time.time() - 10)
        _write_hook_file(tmp_path, payload)

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        result = mw._read_post_tool_use_injection("any_tool")
        assert result is None

    def test_skips_duplicate_sequence(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        # First read with sequence=5
        _write_hook_file(tmp_path, _make_payload(content="first", sequence=5))
        result1 = mw._read_post_tool_use_injection("any_tool")
        assert result1 == "first"

        # Second read with same sequence=5 — should skip
        _write_hook_file(tmp_path, _make_payload(content="dup", sequence=5))
        result2 = mw._read_post_tool_use_injection("any_tool")
        assert result2 is None

    def test_accepts_higher_sequence(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        _write_hook_file(tmp_path, _make_payload(content="first", sequence=1))
        mw._read_post_tool_use_injection("any_tool")

        _write_hook_file(tmp_path, _make_payload(content="second", sequence=2))
        result = mw._read_post_tool_use_injection("any_tool")
        assert result == "second"

    def test_handles_malformed_json(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        hook_dir = tmp_path
        hook_dir.mkdir(parents=True, exist_ok=True)
        (hook_dir / "hook_post_tool_use.json").write_text("not json {{{", encoding="utf-8")

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        result = mw._read_post_tool_use_injection("any_tool")
        assert result is None

    def test_glob_matching_star(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(tool_matcher="*"))
        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        assert mw._read_post_tool_use_injection("anything") is not None

    def test_glob_matching_specific(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(tool_matcher="submit_*"))
        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        result_match = mw._read_post_tool_use_injection("submit_checklist")
        assert result_match is not None

    def test_glob_matching_no_match(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(tool_matcher="submit_*"))
        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        result = mw._read_post_tool_use_injection("read_file")
        assert result is None
        # File should NOT be consumed when tool doesn't match
        assert (tmp_path / "hook_post_tool_use.json").exists()

    def test_missing_inject_key(self, tmp_path: Path) -> None:
        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        payload = {
            "tool_matcher": "*",
            "expires_at": time.time() + 60,
            "sequence": 1,
        }
        _write_hook_file(tmp_path, payload)

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        result = mw._read_post_tool_use_injection("any_tool")
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for on_call_tool
# ---------------------------------------------------------------------------


class TestOnCallTool:
    """Tests for the FastMCP middleware on_call_tool method."""

    @pytest.mark.asyncio
    async def test_appends_injection_to_result(self, tmp_path: Path) -> None:
        from fastmcp.tools.tool import ToolResult

        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(content="[Peer update]: new answer"))

        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        # Mock the FastMCP middleware context
        mock_context = MagicMock()
        mock_context.message.name = "some_tool"

        original_result = ToolResult(content="Original tool output")

        async def mock_call_next(ctx):
            return original_result

        result = await mw.on_call_tool(mock_context, mock_call_next)

        # FastMCP middleware contract: must return ToolResult
        assert isinstance(result, ToolResult)
        texts = [getattr(block, "text", "") for block in result.content]
        assert any("Original tool output" in text for text in texts)
        assert any("[Peer update]: new answer" in text for text in texts)

    @pytest.mark.asyncio
    async def test_passes_through_when_no_injection(self, tmp_path: Path) -> None:
        from fastmcp.tools.tool import ToolResult

        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        mock_context = MagicMock()
        mock_context.message.name = "some_tool"

        original_result = ToolResult(content="Original output")

        async def mock_call_next(ctx):
            return original_result

        result = await mw.on_call_tool(mock_context, mock_call_next)
        assert result is original_result

    @pytest.mark.asyncio
    async def test_wraps_string_result_as_tool_result(self, tmp_path: Path) -> None:
        from fastmcp.tools.tool import ToolResult

        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(content="injected"))

        mw = MassGenHookMiddleware(hook_dir=tmp_path)

        mock_context = MagicMock()
        mock_context.message.name = "tool"

        async def mock_call_next(ctx):
            return "plain string result"

        result = await mw.on_call_tool(mock_context, mock_call_next)
        assert isinstance(result, ToolResult)
        texts = [getattr(block, "text", "") for block in result.content]
        assert any("plain string result" in text for text in texts)
        assert any("injected" in text for text in texts)

    @pytest.mark.asyncio
    async def test_human_input_injection_mirrors_into_structured_content(self, tmp_path: Path) -> None:
        from fastmcp.tools.tool import ToolResult

        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(content="[Human Input]: also include bob dylan"))

        mw = MassGenHookMiddleware(hook_dir=tmp_path)
        mock_context = MagicMock()
        mock_context.message.name = "some_tool"

        original_result = ToolResult(content="Original output", structured_content={"success": True})

        async def mock_call_next(ctx):
            return original_result

        result = await mw.on_call_tool(mock_context, mock_call_next)
        assert isinstance(result, ToolResult)
        assert result.structured_content is not None
        assert result.structured_content["success"] is True
        assert result.structured_content["massgen_runtime_input"] == "[Human Input]: also include bob dylan"
        assert result.structured_content["massgen_runtime_input_priority"] == "high"


class TestToolResultCompatibilityFallback:
    """Ensure fallback path still returns ToolResult-like objects."""

    def test_append_to_result_returns_tool_result_like_when_fastmcp_type_unavailable(self, monkeypatch) -> None:
        import massgen.mcp_tools.hook_middleware as hook_middleware

        monkeypatch.setattr(hook_middleware, "_HAS_FASTMCP_TOOL_RESULT", False)
        monkeypatch.setattr(hook_middleware, "FastMCPToolResult", None)

        result = hook_middleware.MassGenHookMiddleware._append_to_result("base", "inject")

        assert not isinstance(result, list)
        assert hasattr(result, "to_mcp_result")

        mcp_result = result.to_mcp_result()
        assert isinstance(mcp_result, list)
        assert any(getattr(item, "text", "") == "base" for item in mcp_result)
        assert any("inject" in getattr(item, "text", "") for item in mcp_result)

    def test_append_to_result_preserves_structured_content_in_compat_mode(self, monkeypatch) -> None:
        from fastmcp.tools.tool import ToolResult

        import massgen.mcp_tools.hook_middleware as hook_middleware

        monkeypatch.setattr(hook_middleware, "_HAS_FASTMCP_TOOL_RESULT", False)
        monkeypatch.setattr(hook_middleware, "FastMCPToolResult", None)

        base = ToolResult(content="base", structured_content={"ok": True})
        result = hook_middleware.MassGenHookMiddleware._append_to_result(base, "inject")

        assert hasattr(result, "to_mcp_result")
        mcp_result = result.to_mcp_result()
        assert isinstance(mcp_result, tuple)
        content, structured = mcp_result
        assert isinstance(content, list)
        assert structured == {"ok": True}
        assert any("inject" in getattr(item, "text", "") for item in content)


# ---------------------------------------------------------------------------
# Integration: real FastMCP server machinery (in-memory transport)
# ---------------------------------------------------------------------------


class TestRealFastMCPInvocation:
    """Prove the middleware actually fires when added via mcp.add_middleware()
    and a tool is called through real FastMCP machinery.

    This is the in-memory counterpart to the live Codex test. It passes here —
    establishing the middleware LOGIC + wiring are correct — which localizes the
    live-Codex non-delivery to the `fastmcp run <module>:create_server` stdio
    deployment path (where on_call_tool is never invoked), NOT the middleware.
    """

    @pytest.mark.asyncio
    async def test_middleware_injects_via_real_server(self, tmp_path: Path) -> None:
        from fastmcp import Client, FastMCP

        from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

        _write_hook_file(tmp_path, _make_payload(content="[Human Input]: ISO"))

        mcp = FastMCP("iso-test")

        @mcp.tool
        def echo(x: str) -> str:
            return f"echo:{x}"

        mcp.add_middleware(MassGenHookMiddleware(tmp_path))

        async with Client(mcp) as client:
            res = await client.call_tool("echo", {"x": "hi"})

        texts = [getattr(b, "text", "") for b in res.content]
        assert any("echo:hi" in t for t in texts)
        assert any("ISO" in t for t in texts), "middleware did not inject through real FastMCP server"
        # Payload consumed on success.
        assert not (tmp_path / "hook_post_tool_use.json").exists()


class TestStdioDeploymentInvocation:
    """Prove the middleware fires when the server is launched via
    `fastmcp run <module>:create_server` over STDIO — the exact deployment Codex
    uses. Free (local fastmcp subprocess, no model calls). This passing test
    establishes the deployment path is sound, narrowing any live-Codex
    non-delivery to the Codex MCP client / per-server wiring, not the middleware
    or the fastmcp-run/stdio transport.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_middleware_injects_via_fastmcp_run_stdio(self, tmp_path: Path) -> None:
        import shutil
        import textwrap

        if not shutil.which("fastmcp"):
            pytest.skip("fastmcp CLI not on PATH")

        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport

        server_file = tmp_path / "srv.py"
        server_file.write_text(
            textwrap.dedent(
                """
                import os
                from pathlib import Path
                from fastmcp import FastMCP
                from massgen.mcp_tools.hook_middleware import MassGenHookMiddleware

                async def create_server():
                    mcp = FastMCP("iso-stdio")
                    @mcp.tool
                    def echo(x: str) -> str:
                        return f"echo:{x}"
                    mcp.add_middleware(MassGenHookMiddleware(Path(os.environ["ISO_HOOK_DIR"])))
                    return mcp
                """,
            ),
            encoding="utf-8",
        )
        _write_hook_file(tmp_path, _make_payload(content="[Human Input]: STDIO"))

        import os as _os

        env = {**_os.environ, "ISO_HOOK_DIR": str(tmp_path)}
        transport = StdioTransport(command="fastmcp", args=["run", f"{server_file}:create_server"], env=env)
        async with Client(transport) as client:
            res = await client.call_tool("echo", {"x": "hi"})

        texts = [getattr(b, "text", "") for b in res.content]
        assert any("echo:hi" in t for t in texts)
        assert any("STDIO" in t for t in texts), "middleware did not inject via fastmcp-run stdio deployment"
