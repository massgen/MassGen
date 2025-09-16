from __future__ import annotations

"""
Base backend interface for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, AsyncGenerator, Optional
from dataclasses import dataclass
from enum import Enum


class FilesystemSupport(Enum):
    """Types of filesystem support for backends."""

    NONE = "none"  # No filesystem support
    NATIVE = "native"  # Built-in filesystem tools (like Claude Code)
    MCP = "mcp"  # Filesystem support through MCP servers


@dataclass
class StreamChunk:
    """Standardized chunk format for streaming responses."""

    type: str  # "content", "tool_calls", "complete_message", "complete_response", "done", "error", "agent_status", "reasoning", "reasoning_done", "reasoning_summary", "reasoning_summary_done", "backend_status"
    content: Optional[str] = None
    tool_calls: Optional[
        List[Dict[str, Any]]
    ] = None  # User-defined function tools (need execution)
    complete_message: Optional[Dict[str, Any]] = None  # Complete assistant message
    response: Optional[Dict[str, Any]] = None  # Raw Responses API response
    error: Optional[str] = None
    source: Optional[str] = None  # Source identifier (e.g., agent_id, "orchestrator")
    status: Optional[str] = None  # For agent status updates

    # Reasoning-related fields
    reasoning_delta: Optional[str] = None  # Delta text from reasoning stream
    reasoning_text: Optional[str] = None  # Complete reasoning text
    reasoning_summary_delta: Optional[
        str
    ] = None  # Delta text from reasoning summary stream
    reasoning_summary_text: Optional[str] = None  # Complete reasoning summary text
    item_id: Optional[str] = None  # Reasoning item ID
    content_index: Optional[int] = None  # Reasoning content index
    summary_index: Optional[int] = None  # Reasoning summary index


@dataclass
class TokenUsage:
    """Token usage and cost tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class LLMBackend(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.config = kwargs
        self.token_usage = TokenUsage()

        # Filesystem manager integration
        self.filesystem_manager = None
        cwd = kwargs.get("cwd")
        if cwd:
            filesystem_support = self.get_filesystem_support()
            if filesystem_support == FilesystemSupport.MCP:
                # Backend supports MCP - inject filesystem MCP server
                from ..mcp_tools.filesystem_manager import FilesystemManager

                # Get temporary workspace parent from kwargs if available
                temp_workspace_parent = kwargs.get("agent_temporary_workspace")
                # Extract context paths and write access from backend config
                context_paths = kwargs.get("context_paths", [])
                write_access_enabled = kwargs.get("write_access_enabled", False)
                self.filesystem_manager = FilesystemManager(
                    cwd=cwd,
                    agent_temporary_workspace_parent=temp_workspace_parent,
                    context_paths=context_paths,
                    write_access_enabled=write_access_enabled
                )

                # Inject filesystem MCP server into configuration
                self.config = self.filesystem_manager.inject_filesystem_mcp(kwargs)
            elif filesystem_support == FilesystemSupport.NATIVE:
                # Backend has native filesystem support - create manager but don't inject MCP
                from ..mcp_tools.filesystem_manager import FilesystemManager

                # Get temporary workspace parent from kwargs if available
                temp_workspace_parent = kwargs.get("agent_temporary_workspace")
                # Extract context paths and write access from backend config
                context_paths = kwargs.get("context_paths", [])
                write_access_enabled = kwargs.get("write_access_enabled", False)
                self.filesystem_manager = FilesystemManager(
                    cwd=cwd,
                    agent_temporary_workspace_parent=temp_workspace_parent,
                    context_paths=context_paths,
                    write_access_enabled=write_access_enabled
                )
                # Don't inject MCP - native backend handles filesystem tools itself
            elif filesystem_support == FilesystemSupport.NONE:
                raise ValueError(
                    f"Backend {self.get_provider_name()} does not support filesystem operations. Remove 'cwd' from configuration."
                )

            # Auto-register filesystem permission hooks with Function hook system
            if self.filesystem_manager:
                try:
                    from ..mcp_tools.permission_bridge import FilesystemManagerBridge
                    FilesystemManagerBridge.ensure_filesystem_hooks_registered(self)
                except ImportError:
                    pass  # Hook system not available, continue without it
        else:
            self.filesystem_manager = None

    @classmethod
    def get_base_excluded_config_params(cls) -> set:
        """
        Get set of config parameters that are universally handled by base class.

        These are parameters handled by the base class or orchestrator, not passed
        directly to backend implementations. Backends should extend this set with
        their own specific exclusions.

        Returns:
            Set of universal parameter names to exclude from backend options
        """
        return {
            # Filesystem manager parameters (handled by base class)
            "cwd",
            "agent_temporary_workspace",
            "context_paths",
            "write_access_enabled",
            # Backend identification (handled by orchestrator)
            "type",
            "agent_id",
            "session_id",
            # MCP configuration (handled by base class for MCP backends)
            "mcp_servers",
        }

    @abstractmethod
    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a response with tool calling support.

        Args:
            messages: Conversation messages
            tools: Available tools schema
            **kwargs: Additional provider-specific parameters including model

        Yields:
            StreamChunk: Standardized response chunks
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        pass

    @abstractmethod
    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for token usage."""
        pass

    def update_token_usage(
        self, messages: List[Dict[str, Any]], response_content: str, model: str
    ):
        """Update token usage tracking."""
        # Estimate input tokens from messages
        input_text = str(messages)
        input_tokens = self.estimate_tokens(input_text)

        # Estimate output tokens from response
        output_tokens = self.estimate_tokens(response_content)

        # Update totals
        self.token_usage.input_tokens += input_tokens
        self.token_usage.output_tokens += output_tokens

        # Calculate cost
        cost = self.calculate_cost(input_tokens, output_tokens, model)
        self.token_usage.estimated_cost += cost

    def get_token_usage(self) -> TokenUsage:
        """Get current token usage."""
        return self.token_usage

    def reset_token_usage(self):
        """Reset token usage tracking."""
        self.token_usage = TokenUsage()

    def get_filesystem_support(self) -> FilesystemSupport:
        """
        Get the type of filesystem support this backend provides.

        Returns:
            FilesystemSupport: The type of filesystem support
            - NONE: No filesystem capabilities
            - NATIVE: Built-in filesystem tools (like Claude Code)
            - MCP: Can use filesystem through MCP servers
        """
        # By default, backends have no filesystem support
        # Subclasses should override this method
        return FilesystemSupport.NONE

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by this provider."""
        return []

    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """
        Extract tool name from a tool call in this backend's format.

        Args:
            tool_call: Tool call data structure from this backend

        Returns:
            Tool name string
        """
        # Default implementation assumes Chat Completions format
        return tool_call.get("function", {}).get("name", "unknown")

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tool arguments from a tool call in this backend's format.

        Args:
            tool_call: Tool call data structure from this backend

        Returns:
            Tool arguments dictionary
        """
        # Default implementation assumes Chat Completions format
        return tool_call.get("function", {}).get("arguments", {})

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """
        Extract tool call ID from a tool call in this backend's format.

        Args:
            tool_call: Tool call data structure from this backend

        Returns:
            Tool call ID string
        """
        # Default implementation assumes Chat Completions format
        return tool_call.get("id", "")

    def create_tool_result_message(
        self, tool_call: Dict[str, Any], result_content: str
    ) -> Dict[str, Any]:
        """
        Create a tool result message in this backend's expected format.

        Args:
            tool_call: Original tool call data structure
            result_content: The result content to send back

        Returns:
            Tool result message in backend's expected format
        """
        # Default implementation assumes Chat Completions format
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_content}

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """
        Extract the content/output from a tool result message in this backend's format.

        Args:
            tool_result_message: Tool result message created by this backend

        Returns:
            The content/output string from the message
        """
        # Default implementation assumes Chat Completions format
        return tool_result_message.get("content", "")

    def is_stateful(self) -> bool:
        """
        Check if this backend maintains conversation state across requests.

        Returns:
            True if backend is stateful (maintains context), False if stateless

        Stateless backends require full conversation history with each request.
        Stateful backends maintain context internally and only need new messages.
        """
        return False

    def clear_history(self) -> None:
        """
        Clear conversation history while maintaining session.

        For stateless backends, this is a no-op.
        For stateful backends, this clears conversation history but keeps session.
        """
        pass  # Default implementation for stateless backends

    def reset_state(self) -> None:
        """
        Reset backend state for stateful backends.

        For stateless backends, this is a no-op.
        For stateful backends, this clears conversation history and session state.
        """
        pass  # Default implementation for stateless backends
