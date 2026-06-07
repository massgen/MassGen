"""FastMCP middleware for PostToolUse hook injection into MCP tool results.

This middleware reads injection payloads from a file-based IPC channel
and appends them to tool results before returning to the caller (e.g., Codex).

The orchestrator writes hook_post_tool_use.json; the middleware reads and
consumes it. This allows mid-stream injection of peer answers, human input,
and subagent completions without touching individual tool handler code.

File format for hook_post_tool_use.json:
{
  "inject": {"content": "...", "strategy": "tool_result"},
  "tool_matcher": "*",
  "expires_at": 1740000000.0,
  "sequence": 42
}
"""

from __future__ import annotations

import fnmatch
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastmcp.server.middleware import Middleware

logger = logging.getLogger(__name__)

# Import types for ToolResult construction
try:
    import mcp.types as mcp_types

    _HAS_MCP_TYPES = True
except ImportError:
    _HAS_MCP_TYPES = False

try:
    from fastmcp.tools.tool import ToolResult as FastMCPToolResult

    _HAS_FASTMCP_TOOL_RESULT = True
except ImportError:
    FastMCPToolResult = None  # type: ignore[assignment]
    _HAS_FASTMCP_TOOL_RESULT = False


class _CompatToolResult:
    """Compatibility ToolResult for runtimes without fastmcp.tools.tool.ToolResult."""

    def __init__(
        self,
        *,
        content: list[Any],
        structured_content: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.structured_content = structured_content
        self.meta = meta

    def to_mcp_result(self) -> Any:
        if self.meta is not None and _HAS_MCP_TYPES:
            return mcp_types.CallToolResult(
                structuredContent=self.structured_content,
                content=self.content,
                _meta=self.meta,
            )
        if self.structured_content is None:
            return self.content
        return self.content, self.structured_content


class MassGenHookMiddleware(Middleware):
    """FastMCP middleware that injects hook content into MCP tool results.

    Reads hook_post_tool_use.json from a hook directory. When present,
    appends injection content to the tool result before returning to the caller.
    Uses file-based IPC: orchestrator writes, middleware reads and consumes.
    """

    _RUNTIME_INPUT_MARKER = "[Human Input]:"
    _RUNTIME_INPUT_KEY = "massgen_runtime_input"
    _RUNTIME_INPUT_PRIORITY_KEY = "massgen_runtime_input_priority"

    def __init__(self, hook_dir: Path) -> None:
        self._hook_dir = hook_dir
        self._last_post_sequence: int = -1

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        """Intercept tool calls to append injection content to results."""
        tool_name = context.message.name

        # Execute the actual tool
        result = await call_next(context)

        # Check for pending injection — wrapped so injection bugs never
        # break the underlying tool call that already succeeded.
        try:
            injection = self._read_post_tool_use_injection(tool_name)
            if injection:
                result = self._append_to_result(result, injection)
                # Success-path observability (mirrors the error log below). This
                # is how we confirm the middleware actually fires end-to-end in a
                # real run — the CLIs' native hooks can't be trusted to fire, so
                # we log every real injection.
                logger.info(
                    "Hook middleware injected %d chars into '%s' tool result",
                    len(injection),
                    tool_name,
                )
        except Exception as e:
            logger.error(
                "Hook middleware injection failed for tool %s: %s. " "Returning original result.",
                tool_name,
                e,
                exc_info=True,
            )

        return result

    def _read_post_tool_use_injection(self, tool_name: str) -> str | None:
        """Read and conditionally consume hook_post_tool_use.json.

        Returns injection content string if valid and matching, None otherwise.
        The file is consumed (deleted) only when matched and valid.
        """
        hook_file = self._hook_dir / "hook_post_tool_use.json"

        try:
            raw = hook_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(
                "Failed to read hook file %s: %s",
                hook_file,
                e,
            )
            return None

        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Malformed JSON in hook file %s", hook_file)
            # Consume malformed file to prevent re-reading
            hook_file.unlink(missing_ok=True)
            return None

        if not isinstance(payload, dict):
            logger.warning(
                "Hook file %s contains non-dict payload (type=%s); discarding",
                hook_file,
                type(payload).__name__,
            )
            hook_file.unlink(missing_ok=True)
            return None

        # Validate tool_matcher glob against tool_name
        tool_matcher = payload.get("tool_matcher", "*")
        if not fnmatch.fnmatch(tool_name, tool_matcher):
            # Don't consume — a different tool may match later
            return None

        # Validate expiry
        expires_at = payload.get("expires_at")
        if expires_at is not None:
            try:
                if time.time() > float(expires_at):
                    logger.debug("Hook payload expired (expires_at=%s)", expires_at)
                    hook_file.unlink(missing_ok=True)
                    return None
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid expires_at value %r in hook file %s; treating as non-expiring",
                    expires_at,
                    hook_file,
                )

        # Validate sequence (monotonically increasing)
        sequence = payload.get("sequence", 0)
        try:
            sequence = int(sequence)
        except (TypeError, ValueError):
            sequence = 0

        if sequence <= self._last_post_sequence:
            logger.debug(
                "Skipping duplicate sequence %d (last seen: %d)",
                sequence,
                self._last_post_sequence,
            )
            hook_file.unlink(missing_ok=True)
            return None

        # Extract injection content
        inject = payload.get("inject")
        if not isinstance(inject, dict) or not inject.get("content"):
            logger.warning(
                "Hook file %s has missing or empty inject.content; discarding",
                hook_file,
            )
            hook_file.unlink(missing_ok=True)
            return None

        # All checks passed — consume the file and update sequence
        self._last_post_sequence = sequence
        hook_file.unlink(missing_ok=True)

        content = inject["content"]
        logger.info(
            "Hook middleware injecting %d chars into %s result (seq=%d)",
            len(content),
            tool_name,
            sequence,
        )
        return content

    @classmethod
    def _extract_runtime_input_line(cls, injection: str) -> str | None:
        """Extract a normalized runtime-input line from injected text, if present."""
        if cls._RUNTIME_INPUT_MARKER not in injection:
            return None
        _, _, tail = injection.partition(cls._RUNTIME_INPUT_MARKER)
        normalized_tail = tail.strip()
        if not normalized_tail:
            return None
        return f"{cls._RUNTIME_INPUT_MARKER} {normalized_tail}"

    @classmethod
    def _augment_structured_content(
        cls,
        structured_content: dict[str, Any] | None,
        injection: str,
    ) -> dict[str, Any] | None:
        """Mirror human runtime input into structured_content for better salience."""
        runtime_line = cls._extract_runtime_input_line(injection)
        if runtime_line is None:
            return structured_content

        merged: dict[str, Any] = dict(structured_content or {})
        merged[cls._RUNTIME_INPUT_KEY] = runtime_line
        merged[cls._RUNTIME_INPUT_PRIORITY_KEY] = "high"
        return merged

    @staticmethod
    def _append_to_result(result: Any, injection: str) -> Any:
        """Append injection text to the tool result.

        ToolResult in FastMCP is typically a list of content objects or a string.
        We normalize to a list and append a TextContent with the injection.
        """
        # Build the injection content item
        if _HAS_MCP_TYPES:
            injection_item = mcp_types.TextContent(
                type="text",
                text=f"\n{injection}",
            )
        else:
            # Fallback: use a simple string
            injection_item = f"\n{injection}"

        # FastMCP middleware expects a ToolResult-like object from on_call_tool.
        # Returning raw lists causes downstream failures when FastMCP calls
        # result.to_mcp_result().
        def _build_tool_result(
            *,
            content: list[Any],
            structured_content: dict[str, Any] | None = None,
        ) -> Any:
            if _HAS_FASTMCP_TOOL_RESULT and FastMCPToolResult is not None:
                return FastMCPToolResult(
                    content=content,
                    structured_content=structured_content,
                )
            return _CompatToolResult(
                content=content,
                structured_content=structured_content,
            )

        def _with_runtime_structured_content(structured_content: dict[str, Any] | None) -> dict[str, Any] | None:
            return MassGenHookMiddleware._augment_structured_content(
                structured_content,
                injection,
            )

        # Generic ToolResult-like handling (works across FastMCP versions/layouts)
        if hasattr(result, "to_mcp_result") and hasattr(result, "content"):
            return _build_tool_result(
                content=[*list(result.content), injection_item],  # type: ignore[arg-type]
                structured_content=_with_runtime_structured_content(
                    getattr(result, "structured_content", None),
                ),
            )

        if isinstance(result, str):
            if _HAS_MCP_TYPES:
                original_item = mcp_types.TextContent(type="text", text=result)
                return _build_tool_result(
                    content=[original_item, injection_item],
                    structured_content=_with_runtime_structured_content(None),
                )
            return _build_tool_result(
                content=[result, injection_item],
                structured_content=_with_runtime_structured_content(None),
            )
        if isinstance(result, list):
            return _build_tool_result(
                content=[*result, injection_item],
                structured_content=_with_runtime_structured_content(None),
            )
        return _build_tool_result(
            content=[result, injection_item],
            structured_content=_with_runtime_structured_content(None),
        )
