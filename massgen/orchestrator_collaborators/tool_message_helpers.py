"""Tool-message helpers for the coordination/streaming loop.

Three small, cohesive helpers extracted from Orchestrator:

- ``is_tool_related_content`` (``@staticmethod``): defensive check to keep
  tool output / status from leaking into a clean answer text.
- ``create_tool_error_messages``: build a list of per-tool-call error
  result messages (one primary + N secondary), tolerant of backends that
  return either a single dict or a list of result messages per call.
- ``split_disallowed_workflow_tool_calls``: partition raw tool calls into
  allowed vs. disallowed (workflow tools not available this round).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massgen.chat_agent import ChatAgent
    from massgen.orchestrator import Orchestrator


class ToolMessageHelpers:
    """Tool-content classification, error-message creation, and call partitioning."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @staticmethod
    def is_tool_related_content(content: str) -> bool:
        """Return True when ``content`` is tool output/status that should be excluded
        from clean answer text.

        Defensive: normally tool output is handled via mcp_status / backend_status /
        custom_tool_status chunk types, but some backends (e.g. ClaudeCode) can leak
        tool output into content chunks.
        """
        if not content:
            return False
        if content.startswith("🔧 "):
            return True
        if content.startswith("Final Temp Working directory:"):
            return True
        if content.startswith("Final Session ID:"):
            return True
        return False

    @staticmethod
    def create_tool_error_messages(
        agent: ChatAgent,
        tool_calls: list[dict[str, Any]],
        primary_error_msg: str,
        secondary_error_msg: str | None = None,
    ) -> list[dict[str, Any]]:
        """Create tool error messages for all tool calls in a response.

        The first call gets ``primary_error_msg``; additional calls get
        ``secondary_error_msg`` (defaults to primary). Returns a flat list of
        tool-result messages; tolerates backends that return either a single
        dict or a list per call.
        """
        if not tool_calls:
            return []

        if secondary_error_msg is None:
            secondary_error_msg = primary_error_msg

        enforcement_msgs: list[dict[str, Any]] = []

        first_tool_call = tool_calls[0]
        error_result_msg = agent.backend.create_tool_result_message(
            first_tool_call,
            primary_error_msg,
        )
        if isinstance(error_result_msg, list):
            enforcement_msgs.extend(error_result_msg)
        else:
            enforcement_msgs.append(error_result_msg)

        for additional_tool_call in tool_calls[1:]:
            neutral_msg = agent.backend.create_tool_result_message(
                additional_tool_call,
                secondary_error_msg,
            )
            if isinstance(neutral_msg, list):
                enforcement_msgs.extend(neutral_msg)
            else:
                enforcement_msgs.append(neutral_msg)

        return enforcement_msgs

    def split_disallowed_workflow_tool_calls(
        self,
        agent: ChatAgent,
        tool_calls: list[dict[str, Any]],
        allowed_workflow_tool_names: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Split tool calls into allowed and disallowed workflow calls for this round."""
        # Lazy lookup so tests can patch massgen.orchestrator.WORKFLOW_TOOL_NAMES.
        from massgen import orchestrator as _orch_mod

        allowed_calls: list[dict[str, Any]] = []
        disallowed_calls: list[dict[str, Any]] = []
        disallowed_names: list[str] = []

        for tool_call in tool_calls:
            tool_name = agent.backend.extract_tool_name(tool_call)
            if tool_name in _orch_mod.WORKFLOW_TOOL_NAMES and tool_name not in allowed_workflow_tool_names:
                disallowed_calls.append(tool_call)
                disallowed_names.append(tool_name)
                continue
            allowed_calls.append(tool_call)

        return allowed_calls, disallowed_calls, disallowed_names
