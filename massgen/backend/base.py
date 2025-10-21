# -*- coding: utf-8 -*-
"""
Base backend interface for LLM providers.
"""
# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from ..filesystem_manager import FilesystemManager, PathPermissionManagerHook
from ..mcp_tools.hooks import FunctionHookManager, HookType
from ..token_manager import TokenCostCalculator, TokenUsage
from ..utils import CoordinationStage


class FilesystemSupport(Enum):
    """Types of filesystem support for backends."""

    NONE = "none"  # No filesystem support
    NATIVE = "native"  # Built-in filesystem tools (like Claude Code)
    MCP = "mcp"  # Filesystem support through MCP servers


@dataclass
class StreamChunk:
    """Standardized chunk format for streaming responses."""

    type: str  # "content", "tool_calls", "complete_message", "complete_response", "done",
    # "error", "agent_status", "reasoning", "reasoning_done", "reasoning_summary",
    # "reasoning_summary_done", "backend_status"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None  # User-defined function tools (need execution)
    complete_message: Optional[Dict[str, Any]] = None  # Complete assistant message
    response: Optional[Dict[str, Any]] = None  # Raw Responses API response
    error: Optional[str] = None
    source: Optional[str] = None  # Source identifier (e.g., agent_id, "orchestrator")
    status: Optional[str] = None  # For agent status updates

    # Reasoning-related fields
    reasoning_delta: Optional[str] = None  # Delta text from reasoning stream
    reasoning_text: Optional[str] = None  # Complete reasoning text
    reasoning_summary_delta: Optional[str] = None  # Delta text from reasoning summary stream
    reasoning_summary_text: Optional[str] = None  # Complete reasoning summary text
    item_id: Optional[str] = None  # Reasoning item ID
    content_index: Optional[int] = None  # Reasoning content index
    summary_index: Optional[int] = None  # Reasoning summary index


class LLMBackend(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.config = kwargs

        # Initialize utility classes
        self.token_usage = TokenUsage()

        # # Initialize tool manager
        # self.custom_tool_manager = ToolManager()

        # # Register custom tools if specified
        # custom_tools = kwargs.get("custom_tools", [])
        # if custom_tools:
        #     self._register_custom_tools(custom_tools)

        # Planning mode flag - when True, MCP tools should be blocked during coordination
        self._planning_mode_enabled: bool = False

        self.token_calculator = TokenCostCalculator()

        # Filesystem manager integration
        self.filesystem_manager = None
        cwd = kwargs.get("cwd")
        if cwd:
            filesystem_support = self.get_filesystem_support()
            if filesystem_support in (FilesystemSupport.MCP, FilesystemSupport.NATIVE):
                # Validate execution mode
                execution_mode = kwargs.get("command_line_execution_mode", "local")
                if execution_mode not in ["local", "docker"]:
                    raise ValueError(
                        f"Invalid command_line_execution_mode: '{execution_mode}'. Must be 'local' or 'docker'.",
                    )

                # Validate network mode
                network_mode = kwargs.get("command_line_docker_network_mode", "none")
                if network_mode not in ["none", "bridge", "host"]:
                    raise ValueError(
                        f"Invalid command_line_docker_network_mode: '{network_mode}'. Must be 'none', 'bridge', or 'host'.",
                    )

                # Extract all FilesystemManager parameters from kwargs
                filesystem_params = {
                    "cwd": cwd,
                    "agent_temporary_workspace_parent": kwargs.get("agent_temporary_workspace"),
                    "context_paths": kwargs.get("context_paths", []),
                    "context_write_access_enabled": kwargs.get("context_write_access_enabled", False),
                    "enable_image_generation": kwargs.get("enable_image_generation", False),
                    "enable_mcp_command_line": kwargs.get("enable_mcp_command_line", False),
                    "command_line_allowed_commands": kwargs.get("command_line_allowed_commands"),
                    "command_line_blocked_commands": kwargs.get("command_line_blocked_commands"),
                    "command_line_execution_mode": execution_mode,
                    "command_line_docker_image": kwargs.get("command_line_docker_image", "massgen/mcp-runtime:latest"),
                    "command_line_docker_memory_limit": kwargs.get("command_line_docker_memory_limit"),
                    "command_line_docker_cpu_limit": kwargs.get("command_line_docker_cpu_limit"),
                    "command_line_docker_network_mode": network_mode,
                    "enable_audio_generation": kwargs.get("enable_audio_generation", False),
                }

                # Create FilesystemManager
                self.filesystem_manager = FilesystemManager(**filesystem_params)

                # Inject MCP filesystem server for MCP backends only
                if filesystem_support == FilesystemSupport.MCP:
                    self.config = self.filesystem_manager.inject_filesystem_mcp(kwargs)
                # NATIVE backends handle filesystem tools themselves, but need command_line MCP for docker mode
                elif filesystem_support == FilesystemSupport.NATIVE and execution_mode == "docker" and kwargs.get("enable_mcp_command_line", False):
                    self.config = self.filesystem_manager.inject_command_line_mcp(kwargs)

            elif filesystem_support == FilesystemSupport.NONE:
                raise ValueError(f"Backend {self.get_provider_name()} does not support filesystem operations. Remove 'cwd' from configuration.")

            # Auto-setup permission hooks for function-based backends (default)
            if self.filesystem_manager:
                self._setup_permission_hooks()
        else:
            self.filesystem_manager = None

        self.formatter = None
        self.api_params_handler = None
        self.coordination_stage = None

    # def _register_custom_tools(self, tool_names: list[str]) -> None:
    #     """Register custom tool functions.

    #     Args:
    #         tool_names: List of tool names to register
    #     """
    #     import importlib

    #     for tool_name in tool_names:
    #         try:
    #             # Try to import from tool module
    #             module = importlib.import_module("massgen.tool")
    #             if hasattr(module, tool_name):
    #                 tool_func = getattr(module, tool_name)
    #                 self.custom_tool_manager.add_tool_function(tool_func)
    #                 print(f"Successfully registered custom tool: {tool_name}")
    #             else:
    #                 print(f"Warning: Tool '{tool_name}' not found in massgen.tool")
    #         except ImportError as e:
    #             print(f"Warning: Could not import tool module: {e}")
    #         except Exception as e:
    #             print(f"Error registering tool '{tool_name}': {e}")

    def _setup_permission_hooks(self):
        """Setup permission hooks for function-based backends (default behavior)."""
        # Create per-agent hook manager
        self.function_hook_manager = FunctionHookManager()

        # Create permission hook using the filesystem manager's permission manager
        permission_hook = PathPermissionManagerHook(self.filesystem_manager.path_permission_manager)

        # Register hook on this agent's hook manager only
        self.function_hook_manager.register_global_hook(HookType.PRE_CALL, permission_hook)

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
            "context_write_access_enabled",
            "enable_image_generation",
            "enable_mcp_command_line",
            "command_line_allowed_commands",
            "command_line_blocked_commands",
            "command_line_execution_mode",
            "command_line_docker_image",
            "command_line_docker_memory_limit",
            "command_line_docker_cpu_limit",
            "command_line_docker_network_mode",
            # Backend identification (handled by orchestrator)
            "type",
            "agent_id",
            "session_id",
            # MCP configuration (handled by base class for MCP backends)
            "mcp_servers",
        }

    @abstractmethod
    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a response with tool calling support.

        Args:
            messages: Conversation messages
            tools: Available tools schema
            **kwargs: Additional provider-specific parameters including model

        Yields:
            StreamChunk: Standardized response chunks
        """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this provider."""

    def estimate_tokens(self, text: Union[str, List[Dict[str, Any]]], method: str = "auto") -> int:
        """
        Estimate token count for text or messages.

        Args:
            text: Text string or list of message dictionaries
            method: Estimation method ("tiktoken", "simple", "auto")

        Returns:
            Estimated token count
        """
        return self.token_calculator.estimate_tokens(text, method)

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate cost for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name

        Returns:
            Estimated cost in USD
        """
        provider = self.get_provider_name()
        return self.token_calculator.calculate_cost(input_tokens, output_tokens, provider, model)

    def update_token_usage(self, messages: List[Dict[str, Any]], response_content: str, model: str) -> TokenUsage:
        """
        Update token usage tracking.

        Args:
            messages: Input messages
            response_content: Response content
            model: Model name

        Returns:
            Updated TokenUsage object
        """
        provider = self.get_provider_name()
        self.token_usage = self.token_calculator.update_token_usage(self.token_usage, messages, response_content, provider, model)
        return self.token_usage

    def get_token_usage(self) -> TokenUsage:
        """Get current token usage."""
        return self.token_usage

    def reset_token_usage(self):
        """Reset token usage tracking."""
        self.token_usage = TokenUsage()

    def format_cost(self, cost: float = None) -> str:
        """Format cost for display."""
        if cost is None:
            cost = self.token_usage.estimated_cost
        return self.token_calculator.format_cost(cost)

    def format_usage_summary(self, usage: TokenUsage = None) -> str:
        """Format token usage summary for display."""
        if usage is None:
            usage = self.token_usage
        return self.token_calculator.format_usage_summary(usage)

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
        Extract tool name from a tool call (handles multiple formats).

        Supports:
        - Chat Completions format: {"function": {"name": "...", ...}}
        - Response API format: {"name": "..."}
        - Claude native format: {"name": "..."}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool name string
        """
        # Chat Completions format
        if "function" in tool_call:
            return tool_call.get("function", {}).get("name", "unknown")
        # Response API / Claude native format
        elif "name" in tool_call:
            return tool_call.get("name", "unknown")
        # Fallback
        return "unknown"

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tool arguments from a tool call (handles multiple formats).

        Supports:
        - Chat Completions format: {"function": {"arguments": ...}}
        - Response API format: {"arguments": ...}
        - Claude native format: {"input": ...}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool arguments dictionary (parsed from JSON string if needed)
        """
        import json

        # Chat Completions format
        if "function" in tool_call:
            args = tool_call.get("function", {}).get("arguments", {})
        # Claude native format
        elif "input" in tool_call:
            args = tool_call.get("input", {})
        # Response API format
        elif "arguments" in tool_call:
            args = tool_call.get("arguments", {})
        else:
            args = {}

        # Parse JSON string if needed
        if isinstance(args, str):
            try:
                return json.loads(args) if args.strip() else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        return args if isinstance(args, dict) else {}

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """
        Extract tool call ID from a tool call (handles multiple formats).

        Supports:
        - Chat Completions format: {"id": "..."}
        - Response API format: {"call_id": "..."}
        - Claude native format: {"id": "..."}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool call ID string
        """
        # Check for Response API format
        if "call_id" in tool_call:
            return tool_call.get("call_id", "")
        # Check for Chat Completions format or Claude native format (both use "id")
        elif "id" in tool_call:
            return tool_call.get("id", "")
        else:
            return ""

    def create_tool_result_message(self, tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
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

    def reset_state(self) -> None:
        """
        Reset backend state for stateful backends.

        For stateless backends, this is a no-op.
        For stateful backends, this clears conversation history and session state.
        """
        pass  # Default implementation for stateless backends

    def set_planning_mode(self, enabled: bool) -> None:
        """
        Enable or disable planning mode for this backend.

        When planning mode is enabled, MCP tools should be blocked to prevent
        execution during coordination phase.

        Args:
            enabled: True to enable planning mode (block MCP tools), False to disable
        """
        self._planning_mode_enabled = enabled

    def is_planning_mode_enabled(self) -> bool:
        """
        Check if planning mode is currently enabled.

        Returns:
            True if planning mode is enabled (MCP tools should be blocked)
        """
        return self._planning_mode_enabled

    async def _cleanup_client(self, client: Any) -> None:
        """Clean up OpenAI client resources."""
        try:
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()
        except Exception:
            pass

    def set_stage(self, stage: CoordinationStage) -> None:
        """
        Set the current coordination stage for the backend.

        Args:
            stage: CoordinationStage enum value
        """
        self.coordination_stage = stage
