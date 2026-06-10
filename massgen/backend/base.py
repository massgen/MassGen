"""
Base backend interface for LLM providers.
"""

# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..filesystem_manager import FilesystemManager, PathPermissionManagerHook
from ..mcp_tools.hooks import FunctionHookManager, HookType
from ..token_manager import (
    APICallMetric,
    RoundTokenUsage,
    TokenCostCalculator,
    TokenUsage,
)
from ..utils import CoordinationStage
from ..utils.tool_argument_normalization import normalize_json_object_argument
from ._excluded_params import BASE_EXCLUDED_CONFIG_PARAMS

logger = logging.getLogger(__name__)


class FilesystemSupport(Enum):
    """Types of filesystem support for backends."""

    NONE = "none"  # No filesystem support
    NATIVE = "native"  # Built-in filesystem tools (like Claude Code)
    MCP = "mcp"  # Filesystem support through MCP servers


def get_multimodal_tool_definitions() -> list[dict[str, Any]]:
    """Return the standard multimodal custom tool definitions (read_media, generate_media).

    Used by backends that need to register multimodal tools when enable_multimodal_tools is true.
    """
    return [
        {
            "name": ["read_media"],
            "category": "multimodal",
            "path": "massgen/tool/_multimodal_tools/read_media.py",
            "function": ["read_media"],
        },
        {
            "name": ["generate_media"],
            "category": "multimodal",
            "path": "massgen/tool/_multimodal_tools/generation/generate_media.py",
            "function": ["generate_media"],
        },
    ]


@dataclass
class StreamChunk:
    """Standardized chunk format for streaming responses."""

    type: str  # "content", "tool_calls", "complete_message", "complete_response", "done",
    # "error", "agent_status", "reasoning", "reasoning_done", "reasoning_summary",
    # "reasoning_summary_done", "backend_status", "compression_status"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None  # User-defined function tools (need execution)
    complete_message: dict[str, Any] | None = None  # Complete assistant message
    response: dict[str, Any] | None = None  # Raw Responses API response
    usage: dict[str, Any] | None = None  # Token usage metadata (prompt/completion/total)
    error: str | None = None
    source: str | None = None  # Source identifier (e.g., agent_id, "orchestrator")
    status: str | None = None  # For agent status updates
    detail: str | None = None  # Additional detail for status updates

    # Reasoning-related fields
    reasoning_delta: str | None = None  # Delta text from reasoning stream
    reasoning_text: str | None = None  # Complete reasoning text
    reasoning_summary_delta: str | None = None  # Delta text from reasoning summary stream
    reasoning_summary_text: str | None = None  # Complete reasoning summary text
    item_id: str | None = None  # Reasoning item ID
    content_index: int | None = None  # Reasoning content index
    summary_index: int | None = None  # Reasoning summary index

    # Hook execution info (for "hook_execution" type chunks)
    hook_info: dict[str, Any] | None = None  # Hook execution details for display
    tool_call_id: str | None = None  # ID of tool call this hook is attached to

    # Checkpoint event fields (for "checkpoint_activated" / "checkpoint_completed" type chunks)
    checkpoint_participants: dict[str, Any] | None = None  # display_id -> {real_agent_id, model}
    checkpoint_number: int | None = None  # Sequential checkpoint number
    main_agent_id: str | None = None  # The delegating agent's real ID

    # Display flag - reserved for future use (not yet consumed by any handler)
    display: bool = True


class LLMBackend(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str | None = None, **kwargs):
        self.api_key = api_key

        # Extract and remove instance_id before storing config (used only for Docker, not for API calls)
        self._instance_id = kwargs.pop("instance_id", None)

        self.config = kwargs

        # Initialize utility classes
        self.token_usage = TokenUsage()

        # Track last API call's input tokens (for compression decisions)
        # This is different from token_usage.input_tokens which is cumulative
        self._last_call_input_tokens: int = 0

        # Round-level token tracking
        self._round_token_history: list[RoundTokenUsage] = []
        self._current_round_number: int = 0
        self._current_round_type: str = ""
        self._round_start_snapshot: dict[str, Any] | None = None
        self._round_start_tool_count: int = 0
        self._round_used_fallback_estimation: bool = False  # Track if fallback was used in current round

        # API call timing (pure LLM time, excluding tool execution)
        self._api_call_history: list[APICallMetric] = []
        self._current_api_call: APICallMetric | None = None
        self._api_call_index: int = 0
        self._current_agent_id: str | None = None

        # # Initialize tool manager
        # self.custom_tool_manager = ToolManager()

        # # Register custom tools if specified
        # custom_tools = kwargs.get("custom_tools", [])
        # if custom_tools:
        #     self._register_custom_tools(custom_tools)

        # Planning mode flag - when True, MCP tools should be blocked during coordination
        self._planning_mode_enabled: bool = False

        # Selective tool blocking - list of specific MCP tools to block during planning mode
        # When planning_mode is enabled, only these specific tools are blocked
        # If empty, ALL MCP tools are blocked (backward compatible behavior)
        self._planning_mode_blocked_tools: set = set()

        self.token_calculator = TokenCostCalculator()

        # Compression target ratio for reactive compression (context limit recovery)
        # Default 0.2 = preserve 20% of messages, summarize 80%
        # This is set by Orchestrator from CoordinationConfig.compression_target_ratio
        self._compression_target_ratio: float = 0.20

        # Filesystem manager integration
        self.filesystem_manager = None
        cwd = kwargs.get("cwd")
        if cwd:
            filesystem_support = self.get_filesystem_support()
            if filesystem_support in (FilesystemSupport.MCP, FilesystemSupport.NATIVE):
                # Validate execution mode
                execution_mode = kwargs.get("command_line_execution_mode", "local")
                if execution_mode not in ["local", "docker", "srt"]:
                    raise ValueError(
                        f"Invalid command_line_execution_mode: '{execution_mode}'. Must be 'local', 'docker', or 'srt'.",
                    )

                # Backends with a native execution sandbox (codex, claude_code) must
                # not be SRT-wrapped: SRT (Seatbelt/bubblewrap) would nest inside the
                # backend's own sandbox and hang. Degrade srt -> local; the backend's
                # native sandbox provides the isolation. (SRT targets backends without
                # one — e.g. OpenAI/Claude/Gemini/Grok API backends via the MCP.)
                if execution_mode == "srt" and self.has_native_execution_sandbox():
                    logger.warning(
                        f"[{self.get_provider_name()}] command_line_execution_mode 'srt' ignored — this backend "
                        "has a native execution sandbox; using its own isolation (SRT would nest sandboxes). "
                        "Falling back to 'local' for MassGen's command-line MCP.",
                    )
                    execution_mode = "local"
                    # Normalize the stored config too, so downstream RAW reads of
                    # command_line_execution_mode (e.g. claude_code disallowed-tools /
                    # system-prompt logic) see the effective 'local', not 'srt'.
                    kwargs["command_line_execution_mode"] = "local"

                # Validate network mode
                network_mode = kwargs.get("command_line_docker_network_mode", "none")
                if network_mode not in ["none", "bridge", "host"]:
                    raise ValueError(
                        f"Invalid command_line_docker_network_mode: '{network_mode}'. Must be 'none', 'bridge', or 'host'.",
                    )

                # Validate SRT read-confinement mode
                srt_read_mode = kwargs.get("command_line_srt_read_mode", "confined")
                if srt_read_mode not in ["confined", "strict", "open"]:
                    raise ValueError(
                        f"Invalid command_line_srt_read_mode: '{srt_read_mode}'. Must be 'confined', 'strict', or 'open'.",
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
                    "command_line_docker_image": kwargs.get("command_line_docker_image", "ghcr.io/massgen/mcp-runtime:latest"),
                    "command_line_docker_memory_limit": kwargs.get("command_line_docker_memory_limit"),
                    "command_line_docker_cpu_limit": kwargs.get("command_line_docker_cpu_limit"),
                    "command_line_docker_network_mode": network_mode,
                    "command_line_docker_enable_sudo": kwargs.get("command_line_docker_enable_sudo", False),
                    # Nested credential and package management
                    "command_line_docker_credentials": kwargs.get("command_line_docker_credentials"),
                    "command_line_docker_packages": kwargs.get("command_line_docker_packages"),
                    # SRT (OS-level sandbox-runtime) execution mode. Network defaults to
                    # deny-all; an allowlisted domain is an opt-in capability grant.
                    "command_line_srt_network_allowed_domains": kwargs.get("command_line_srt_network_allowed_domains", []),
                    "command_line_srt_deny_read": kwargs.get("command_line_srt_deny_read", []),
                    "command_line_srt_allow_unix_sockets": kwargs.get("command_line_srt_allow_unix_sockets", []),
                    # Read confinement: "confined" (default) denies $HOME, re-allows
                    # managed paths; "strict" denies "/"; "open" allows-all minus secrets.
                    "command_line_srt_read_mode": srt_read_mode,
                    "command_line_srt_allow_read": kwargs.get("command_line_srt_allow_read", []),
                    "enable_audio_generation": kwargs.get("enable_audio_generation", False),
                    "exclude_file_operation_mcps": kwargs.get("exclude_file_operation_mcps", False),
                    "use_mcpwrapped_for_tool_filtering": kwargs.get("use_mcpwrapped_for_tool_filtering", False),
                    "use_no_roots_wrapper": kwargs.get("use_no_roots_wrapper", False),
                    "enable_code_based_tools": kwargs.get("enable_code_based_tools", False),
                    "custom_tools_path": kwargs.get("custom_tools_path"),
                    "auto_discover_custom_tools": kwargs.get("auto_discover_custom_tools", False),
                    "exclude_custom_tools": kwargs.get("exclude_custom_tools"),
                    "direct_mcp_servers": kwargs.get("direct_mcp_servers"),
                    "shared_tools_directory": kwargs.get("shared_tools_directory"),
                    # Instance ID for parallel execution (Docker container naming)
                    "instance_id": self._instance_id,
                    # Session mount support for multi-turn Docker
                    "filesystem_session_id": kwargs.get("filesystem_session_id"),
                    "session_storage_base": kwargs.get("session_storage_base"),
                    # Two-tier workspace (scratch/deliverable) + git versioning
                    "use_two_tier_workspace": kwargs.get("use_two_tier_workspace", False),
                    # Write mode for worktree isolation (suppresses Docker context mounts)
                    "write_mode": kwargs.get("write_mode"),
                }

                # Create FilesystemManager
                self.filesystem_manager = FilesystemManager(**filesystem_params)

                # Inject MCP filesystem server for MCP backends only
                if filesystem_support == FilesystemSupport.MCP:
                    self.config = self.filesystem_manager.inject_filesystem_mcp(kwargs)
                # NATIVE backends handle filesystem tools themselves, but need command_line MCP for execution
                elif filesystem_support == FilesystemSupport.NATIVE and kwargs.get("enable_mcp_command_line", False):
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
    def get_base_excluded_config_params(cls) -> set[str]:
        """
        Get set of config parameters that are universally handled by base class.

        These are parameters handled by the base class or orchestrator, not passed
        directly to backend implementations. Backends should extend this set with
        their own specific exclusions.

        Returns:
            Set of universal parameter names to exclude from backend options
        """
        return set(BASE_EXCLUDED_CONFIG_PARAMS)

    @abstractmethod
    async def stream_with_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk]:
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

    def estimate_tokens(self, text: str | list[dict[str, Any]], method: str = "auto") -> int:
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

    def update_token_usage(self, messages: list[dict[str, Any]], response_content: str, model: str) -> TokenUsage:
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

    # ==================== Round Token Tracking ====================

    def start_round_tracking(self, round_number: int, round_type: str, agent_id: str = "") -> None:
        """Mark the start of a new round for token tracking.

        Args:
            round_number: The coordination round number
            round_type: Type of round ("initial_answer", "enforcement", "presentation")
            agent_id: The agent ID for this round
        """
        logger.info(
            f"[{self.get_provider_name()}] start_round_tracking: round={round_number}, type={round_type}, agent={agent_id}, "
            f"current_tokens=(in={self.token_usage.input_tokens}, out={self.token_usage.output_tokens})",
        )
        self._current_round_number = round_number
        self._current_round_type = round_type
        # Snapshot current totals for delta calculation
        self._round_start_snapshot = {
            "input_tokens": self.token_usage.input_tokens,
            "output_tokens": self.token_usage.output_tokens,
            "reasoning_tokens": self.token_usage.reasoning_tokens,
            "cached_input_tokens": self.token_usage.cached_input_tokens,
            "estimated_cost": self.token_usage.estimated_cost,
            "start_time": time.time(),
            "agent_id": agent_id,
        }
        # Track tool count at start (for tools executed in this round)
        if hasattr(self, "_tool_execution_metrics"):
            self._round_start_tool_count = len(self._tool_execution_metrics)
        else:
            self._round_start_tool_count = 0

        # Reset fallback tracking for this round
        self._round_used_fallback_estimation = False

        # Update round number for tool metrics (so tools know which round they're in)
        if hasattr(self, "set_round_number"):
            self.set_round_number(round_number)

    def end_round_tracking(self, outcome: str) -> RoundTokenUsage | None:
        """Mark end of round and calculate delta tokens.

        Args:
            outcome: How the round ended ("answer", "vote", "restarted", "timeout", "error")

        Returns:
            RoundTokenUsage for the completed round, or None if no round was started
        """
        if self._round_start_snapshot is None:
            logger.warning(
                f"[{self.get_provider_name()}] end_round_tracking({outcome}): _round_start_snapshot is None! "
                f"No round was started. Current tokens=(in={self.token_usage.input_tokens}, out={self.token_usage.output_tokens})",
            )
            return None

        logger.info(
            f"[{self.get_provider_name()}] end_round_tracking({outcome}): "
            f"snapshot_tokens=(in={self._round_start_snapshot['input_tokens']}, out={self._round_start_snapshot['output_tokens']}), "
            f"current_tokens=(in={self.token_usage.input_tokens}, out={self.token_usage.output_tokens})",
        )

        # Calculate tool calls in this round
        tool_calls = 0
        if hasattr(self, "_tool_execution_metrics"):
            tool_calls = len(self._tool_execution_metrics) - self._round_start_tool_count

        # Calculate context window usage percentage using this round's input tokens
        context_window_size = 0
        context_usage_pct = 0.0
        round_input_tokens = self.token_usage.input_tokens - self._round_start_snapshot["input_tokens"]
        model = self.config.get("model", "")
        pricing = self.token_calculator.get_model_pricing(self.get_provider_name(), model)
        if pricing and pricing.context_window:
            context_window_size = pricing.context_window
            if context_window_size > 0:
                context_usage_pct = (round_input_tokens / context_window_size) * 100

        # Determine token source: "api" if we got real data, "estimated" if we used fallback
        token_source = "estimated" if self._round_used_fallback_estimation else "api"

        # Create RoundTokenUsage with deltas
        round_usage = RoundTokenUsage(
            round_number=self._current_round_number,
            agent_id=self._round_start_snapshot.get("agent_id", ""),
            round_type=self._current_round_type,
            outcome=outcome,
            input_tokens=self.token_usage.input_tokens - self._round_start_snapshot["input_tokens"],
            output_tokens=self.token_usage.output_tokens - self._round_start_snapshot["output_tokens"],
            reasoning_tokens=self.token_usage.reasoning_tokens - self._round_start_snapshot["reasoning_tokens"],
            cached_input_tokens=self.token_usage.cached_input_tokens - self._round_start_snapshot["cached_input_tokens"],
            estimated_cost=self.token_usage.estimated_cost - self._round_start_snapshot["estimated_cost"],
            context_window_size=context_window_size,
            context_usage_pct=context_usage_pct,
            tool_calls_count=tool_calls,
            token_source=token_source,
            start_time=self._round_start_snapshot["start_time"],
            end_time=time.time(),
        )

        self._round_token_history.append(round_usage)
        self._round_start_snapshot = None
        logger.info(
            f"[{self.get_provider_name()}] Round {round_usage.round_number} ({outcome}) recorded: "
            f"delta_tokens=(in={round_usage.input_tokens}, out={round_usage.output_tokens}), "
            f"history_length={len(self._round_token_history)}",
        )
        return round_usage

    def get_round_token_history(self) -> list[dict[str, Any]]:
        """Get token usage history by round."""
        return [r.to_dict() for r in self._round_token_history]

    def get_current_round_number(self) -> int:
        """Get the current round number."""
        return self._current_round_number

    def get_current_round_type(self) -> str:
        """Get the current round type (e.g., 'initial_answer', 'voting', 'presentation')."""
        return self._current_round_type

    # ==============================================================
    # API Call Timing
    # ==============================================================

    def set_current_agent_id(self, agent_id: str) -> None:
        """Set the current agent ID for API call tracking."""
        self._current_agent_id = agent_id

    def start_api_call_timing(self, model: str) -> None:
        """Start timing an API call.

        Call this immediately before making the API request.

        Args:
            model: The model name being called
        """
        self._current_api_call = APICallMetric(
            agent_id=self._current_agent_id or "unknown",
            round_number=self._current_round_number,
            call_index=self._api_call_index,
            backend_name=self.get_provider_name(),
            model=model,
            start_time=time.time(),
        )

    def record_first_token(self) -> None:
        """Record time to first token (TTFT).

        Call this when the first content token is received from the stream.
        Only records the first call per API request.
        """
        if self._current_api_call and self._current_api_call.time_to_first_token_ms == 0:
            self._current_api_call.time_to_first_token_ms = (time.time() - self._current_api_call.start_time) * 1000

    def end_api_call_timing(self, success: bool = True, error: str | None = None) -> None:
        """End timing and record the API call.

        Call this when the stream completes or an error occurs.

        Args:
            success: Whether the API call completed successfully
            error: Error message if the call failed
        """
        if self._current_api_call:
            self._current_api_call.end_time = time.time()
            self._current_api_call.success = success
            self._current_api_call.error_message = error
            self._api_call_history.append(self._current_api_call)
            self._api_call_index += 1
            logger.debug(
                f"[{self.get_provider_name()}] API call completed: "
                f"duration={self._current_api_call.duration_ms:.0f}ms, "
                f"ttft={self._current_api_call.time_to_first_token_ms:.0f}ms, "
                f"success={success}",
            )
            self._current_api_call = None

    def get_api_call_history(self) -> list[APICallMetric]:
        """Get all API call metrics.

        Returns:
            List of APICallMetric objects for all API calls made by this backend
        """
        return self._api_call_history

    def reset_api_call_tracking_for_round(self) -> None:
        """Reset API call index for a new round.

        Call this at the start of each coordination round to reset the call index.
        """
        self._api_call_index = 0

    # ==============================================================

    def _update_token_usage_from_api_response(self, usage: Any, model: str) -> None:
        """Standardized token usage update from API response.

        This is the primary method backends should use to update token tracking.
        It handles all provider formats and updates both cost and detailed token breakdowns.

        Args:
            usage: Usage object or dict from API response
            model: Model name for pricing lookup
        """
        if usage is None:
            return

        # Check if provider returned cost directly (e.g., OpenRouter includes 'cost' field)
        # This takes priority over litellm calculation since it's the actual billed cost
        provider_cost = None
        if isinstance(usage, dict):
            provider_cost = usage.get("cost")
        elif hasattr(usage, "cost"):
            provider_cost = getattr(usage, "cost", None)

        if provider_cost is not None and provider_cost > 0:
            cost = provider_cost
            logger.info(f"[{self.__class__.__name__}] Cost ${cost:.6f} from API response (model: {model})")
        else:
            # Calculate cost using litellm.completion_cost() directly
            cost = self.token_calculator.calculate_cost_with_usage_object(
                model=model,
                usage=usage,
                provider=self.get_provider_name(),
            )
            if cost > 0:
                logger.info(f"[{self.__class__.__name__}] Cost ${cost:.6f} calculated via litellm (model: {model})")

        # Extract detailed token breakdown for visibility
        breakdown = self.token_calculator.extract_token_breakdown(usage)

        # Track last call's input tokens (for compression - need per-call, not cumulative)
        self._last_call_input_tokens = breakdown.get("input_tokens", 0)

        # Update all TokenUsage fields (cumulative)
        self.token_usage.input_tokens += breakdown.get("input_tokens", 0)
        self.token_usage.output_tokens += breakdown.get("output_tokens", 0)
        self.token_usage.estimated_cost += cost
        self.token_usage.reasoning_tokens += breakdown.get("reasoning_tokens", 0)
        self.token_usage.cached_input_tokens += breakdown.get("cached_input_tokens", 0)
        self.token_usage.cache_creation_tokens += breakdown.get("cache_creation_tokens", 0)

        # Warn if cost is 0 but tokens were tracked (model likely not in pricing database)
        input_tokens = breakdown.get("input_tokens", 0)
        output_tokens = breakdown.get("output_tokens", 0)
        if cost == 0 and (input_tokens > 0 or output_tokens > 0):
            logger.warning(
                f"[{self.__class__.__name__}] Cost is $0.00 for model '{model}' with "
                f"{input_tokens} input + {output_tokens} output tokens. "
                f"Model may not be in pricing database (litellm or provider-returned cost).",
            )

    def _estimate_token_usage(self, messages: list[dict[str, Any]], response_content: str, model: str) -> None:
        """Fallback: Estimate tokens for backends without usage data (local models).

        Uses tiktoken for estimation when API doesn't return usage data.

        Args:
            messages: Input messages for token estimation
            response_content: Response content for token estimation
            model: Model name for pricing lookup
        """
        # Mark that we used fallback estimation for this round
        self._round_used_fallback_estimation = True

        input_tokens = self.token_calculator.estimate_tokens(messages)
        output_tokens = self.token_calculator.estimate_tokens(response_content)
        cost = self.token_calculator.calculate_cost(
            input_tokens,
            output_tokens,
            self.get_provider_name(),
            model,
        )

        self.token_usage.input_tokens += input_tokens
        self.token_usage.output_tokens += output_tokens
        self.token_usage.estimated_cost += cost

        logger.info(
            f"[{self.get_provider_name()}] Used fallback token estimation: " f"input={input_tokens}, output={output_tokens}, cost=${cost:.6f}",
        )

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

    def has_native_execution_sandbox(self) -> bool:
        """Whether this backend sandboxes its own command execution natively.

        Backends like Codex (`--full-auto` → Landlock/Seatbelt) and Claude Code
        confine their own command execution. For these, MassGen's OS-level SRT
        sandbox is both redundant and harmful: SRT also uses Seatbelt/bubblewrap,
        and the backend spawns its MCP servers inside its own sandbox, so an
        SRT-wrapped command nests sandboxes and hangs. When True, MassGen degrades
        `command_line_execution_mode: srt` to `local` for this backend (its native
        sandbox provides the isolation). SRT is for backends WITHOUT one.
        """
        return False

    def get_supported_builtin_tools(self) -> list[str]:
        """Get list of builtin tools supported by this provider."""
        return []

    def extract_tool_name(self, tool_call: dict[str, Any]) -> str:
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

    def extract_tool_arguments(self, tool_call: dict[str, Any]) -> dict[str, Any]:
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

        try:
            parsed, decode_passes = normalize_json_object_argument(
                args,
                field_name="arguments",
            )
        except ValueError:
            return {}
        if decode_passes > 1:
            logger.info(
                "[Backend] Normalized %s decode passes while extracting tool arguments",
                decode_passes,
            )
        return parsed

    def extract_tool_call_id(self, tool_call: dict[str, Any]) -> str:
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

    def create_tool_result_message(
        self,
        tool_call: dict[str, Any],
        result_content: str,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Create a tool result message in this backend's expected format.

        Args:
            tool_call: Original tool call data structure
            result_content: The result content to send back

        Returns:
            Tool result message(s) in backend's expected format.
            Most backends return a single dict, but Response API returns a list
            of two dicts (function_call + function_call_output).
        """
        # Default implementation assumes Chat Completions format
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_content}

    def filter_enforcement_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        unknown_tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return tool calls eligible for workflow-enforcement tool_result messages.

        Most backends preserve all tool calls in assistant-message history, so the
        safe default is to return the list unchanged. Backends with stricter API
        requirements can override this and drop calls that were stripped from
        history before enforcement.
        """
        _ = unknown_tool_calls
        return tool_calls

    def extract_tool_result_content(self, tool_result_message: dict[str, Any]) -> str:
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

    # Note: Mid-stream injection is now handled via the hook framework.
    # See MidStreamInjectionHook in mcp_tools/hooks.py

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

    def set_planning_mode_blocked_tools(self, tool_names: set) -> None:
        """
        Set specific MCP tools to block during planning mode.

        This enables selective tool blocking - only the specified tools will be blocked
        when planning mode is enabled, allowing other MCP tools to be used.

        Args:
            tool_names: Set of MCP tool names to block (e.g., {'mcp__discord__discord_send'})
                       If empty set, ALL MCP tools are blocked (backward compatible)
        """
        self._planning_mode_blocked_tools = set(tool_names)

    def get_planning_mode_blocked_tools(self) -> set:
        """
        Get the set of MCP tools currently blocked in planning mode.

        Returns:
            Set of blocked MCP tool names. Empty set means ALL MCP tools are blocked.
        """
        return self._planning_mode_blocked_tools.copy()

    def is_mcp_tool_blocked(self, tool_name: str) -> bool:
        """
        Check if a specific MCP tool is blocked in planning mode.

        Args:
            tool_name: Name of the MCP tool to check (e.g., 'mcp__discord__discord_send')

        Returns:
            True if the tool should be blocked, False otherwise

        Note:
            - If planning mode is disabled, returns False (no blocking)
            - If planning mode is enabled and blocked_tools is empty, returns True (block ALL)
            - If planning mode is enabled and blocked_tools is set, returns True only if tool is in the set
        """
        if not self._planning_mode_enabled:
            return False

        # Empty set means block ALL MCP tools (backward compatible behavior)
        if not self._planning_mode_blocked_tools:
            return True

        # Otherwise, block only if tool is in the blocked set
        return tool_name in self._planning_mode_blocked_tools

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


# ---------------------------------------------------------------------------
# Shared workflow tool helpers (used by Claude Code and Codex backends)
# ---------------------------------------------------------------------------


def extract_structured_response(text: str) -> dict[str, Any] | None:
    """Extract a structured JSON workflow tool call from text.

    Looks for ``{"tool_name": "...", "arguments": {...}}`` in the text,
    trying multiple strategies: markdown code blocks, regex, brace-matching,
    and line-by-line scanning.

    Returns:
        Parsed dict if found, ``None`` otherwise.
    """
    try:
        # Strategy 0: JSON inside ```json code blocks (last match wins)
        markdown_matches = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        for match in reversed(markdown_matches):
            try:
                parsed = json.loads(match.strip())
                if isinstance(parsed, dict) and "tool_name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Strategy 1: Simple regex for JSON objects
        for match in reversed(re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)):
            try:
                parsed = json.loads(match.strip())
                if isinstance(parsed, dict) and "tool_name" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Strategy 2: Brace-matching walk
        brace_count = 0
        json_start = -1
        for i, char in enumerate(text):
            if char == "{":
                if brace_count == 0:
                    json_start = i
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0 and json_start >= 0:
                    try:
                        parsed = json.loads(text[json_start : i + 1])
                        if isinstance(parsed, dict) and "tool_name" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    json_start = -1

        # Strategy 3: Line-by-line fallback
        lines = text.strip().split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            candidate = None
            if stripped.startswith("{") and stripped.endswith("}"):
                candidate = stripped
            elif stripped.startswith("{"):
                parts = stripped
                for j in range(i + 1, len(lines)):
                    parts += "\n" + lines[j].strip()
                    if lines[j].strip().endswith("}"):
                        candidate = parts
                        break
            if candidate:
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

        return None
    except Exception:
        return None


def parse_workflow_tool_calls(
    text: str,
    allowed_tool_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Parse workflow tool calls from accumulated text output.

    Args:
        text: Accumulated text from the agent response.
        allowed_tool_names: If provided, only tool calls whose name is in this
            set are returned.  Calls for tools not in the set are silently
            dropped.  When ``None`` (default), all parsed calls are returned
            for backwards compatibility.

    Returns a list of tool-call dicts in the standard format expected by
    the orchestrator::

        {"id": "call_...", "type": "function",
         "function": {"name": "vote", "arguments": {...}}}
    """
    # Primary path: structured extraction
    structured = extract_structured_response(text)
    if structured and isinstance(structured, dict):
        tool_name = structured.get("tool_name")
        arguments = structured.get("arguments", {})
        if tool_name and isinstance(arguments, dict):
            if allowed_tool_names is not None and tool_name not in allowed_tool_names:
                return []
            return [
                {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": arguments},
                },
            ]

    # Fallback: regex for multiple tool calls
    tool_calls: list[dict[str, Any]] = []
    seen: set = set()
    patterns = [
        r'\{"tool_name":\s*"([^"]+)",\s*"arguments":\s*(\{[^}]*\})\}',
        r'\{\s*"tool_name"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[^}]*\})\s*\}',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            tool_name = match.group(1)
            if allowed_tool_names is not None and tool_name not in allowed_tool_names:
                continue
            try:
                arguments = json.loads(match.group(2))
                sig = (tool_name, json.dumps(arguments, sort_keys=True))
                if sig not in seen:
                    seen.add(sig)
                    tool_calls.append(
                        {
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        },
                    )
            except json.JSONDecodeError:
                continue
    return tool_calls


def build_workflow_instructions(tools: list[dict[str, Any]]) -> str:
    """Build workflow tool instructions for system prompt injection.

    Filters *tools* to workflow tools only and returns the instruction text
    to append to a system prompt.  Returns empty string when no workflow
    tools are present.
    """
    from ..tool.workflow_toolkits.base import WORKFLOW_TOOL_NAMES

    workflow_tools = [t for t in tools if t.get("function", {}).get("name") in WORKFLOW_TOOL_NAMES]
    if not workflow_tools:
        return ""

    parts: list[str] = ["\n--- Coordination Actions ---"]
    for tool in workflow_tools:
        name = tool.get("function", {}).get("name", "unknown")
        description = tool.get("function", {}).get("description", "No description")
        parts.append(f"- {name}: {description}")

        if name == "new_answer":
            parts.append(
                '    Usage: {"tool_name": "new_answer", ' '"arguments": {"content": "your improved answer. If any builtin tools were used, mention how they are used here."}}',
            )
        elif name == "vote":
            agent_id_enum = None
            for t in tools:
                if t.get("function", {}).get("name") == "vote":
                    agent_id_param = t.get("function", {}).get("parameters", {}).get("properties", {}).get("agent_id", {})
                    if "enum" in agent_id_param:
                        agent_id_enum = agent_id_param["enum"]
                    break
            if agent_id_enum:
                agent_list = ", ".join(agent_id_enum)
                parts.append(
                    f'    Usage: {{"tool_name": "vote", "arguments": {{"agent_id": "agent1", ' f'"reason": "explanation"}}}} // Choose agent_id from: {agent_list}',
                )
            else:
                parts.append(
                    '    Usage: {"tool_name": "vote", ' '"arguments": {"agent_id": "agent1", "reason": "explanation"}}',
                )
        elif name == "stop":
            parts.append(
                '    Usage: {"tool_name": "stop", "arguments": {"summary": "Brief summary of completed work", ' '"status": "complete"}}  // status: "complete" or "blocked"',
            )
        elif name == "submit":
            parts.append('    Usage: {"tool_name": "submit", "arguments": {"confirmed": true}}')
        elif name == "restart_orchestration":
            parts.append(
                '    Usage: {"tool_name": "restart_orchestration", ' '"arguments": {"reason": "The answer is incomplete because...", ' '"instructions": "In the next attempt, please..."}}',
            )
        elif name == "ask_others":
            parts.append(
                '    Usage: {"tool_name": "ask_others", ' '"arguments": {"question": "Which framework should we use: Next.js or React?"}}',
            )
            parts.append(
                '    IMPORTANT: When user says "call ask_others" or "ask others", you MUST execute this tool call.',
            )
        elif name == "checkpoint":
            parts.append(
                '    Usage: {"tool_name": "checkpoint", '
                '"arguments": {"task": "What agents should accomplish", '
                '"eval_criteria": ["criterion 1", "criterion 2", "...more as needed"], '
                '"context": "Background info"}}',
            )
            parts.append(
                "    eval_criteria is REQUIRED: provide 3-7 specific, measurable quality criteria " "the team will evaluate against.",
            )

    parts.append("\n--- MassGen Coordination Instructions ---")
    parts.append("IMPORTANT: You must respond with a structured JSON decision at the end of your response.")
    parts.append("The JSON MUST be formatted as a strict JSON code block:")
    parts.append("1. Start with ```json on one line")
    parts.append("2. Include your JSON content (properly formatted)")
    parts.append("3. End with ``` on one line")
    # Dynamic example based on actual tools present (stop in decomposition, vote in voting)
    tool_names_present = {t.get("function", {}).get("name") for t in workflow_tools}
    if "stop" in tool_names_present:
        parts.append(
            'Example format:\n```json\n{"tool_name": "stop", "arguments": {"summary": "Brief summary of completed work", "status": "complete"}}\n```',
        )
    else:
        parts.append(
            'Example format:\n```json\n{"tool_name": "vote", "arguments": {"agent_id": "agent1", "reason": "explanation"}}\n```',
        )
    parts.append("The JSON block should be placed at the very end of your response, after your analysis.")
    return "\n".join(parts)


def build_workflow_mcp_instructions(tools: list[dict[str, Any]], mcp_prefix: str = "") -> str:
    """Build instructions for when workflow tools are available as native MCP tools.

    Unlike build_workflow_instructions() which includes JSON format examples for
    text-based parsing, this version tells the agent to call the MCP tools directly.
    Still needed so the agent knows it MUST call them.

    Args:
        tools: List of tool definitions.
        mcp_prefix: Optional prefix for MCP tool names (e.g., "mcp__massgen_workflow_tools__"
                   for Claude Code). If empty, tools are called by their simple names.
    """
    from ..tool.workflow_toolkits.base import WORKFLOW_TOOL_NAMES

    workflow_tools = [t for t in tools if t.get("function", {}).get("name") in WORKFLOW_TOOL_NAMES]
    if not workflow_tools:
        return ""

    tool_names = [t.get("function", {}).get("name", "") for t in workflow_tools]

    parts: list[str] = ["\n--- MassGen Coordination Instructions ---"]
    parts.append(
        "CRITICAL: You MUST call one of the following MCP tools before finishing your response. " "Do NOT just write text — you must actually invoke the tool.",
    )

    for tool in workflow_tools:
        name = tool.get("function", {}).get("name", "unknown")
        full_name = f"{mcp_prefix}{name}" if mcp_prefix else name
        description = tool.get("function", {}).get("description", "No description")
        parts.append(f"- `{full_name}`: {description}")

        if name == "vote":
            agent_id_param = tool.get("function", {}).get("parameters", {}).get("properties", {}).get("agent_id", {})
            agent_id_enum = agent_id_param.get("enum")
            if agent_id_enum:
                parts.append(f"    Valid agent_id values: {', '.join(agent_id_enum)}")

    # Use prefixed names in instructions
    new_answer_name = f"`{mcp_prefix}new_answer`" if mcp_prefix else "`new_answer`"
    vote_name = f"`{mcp_prefix}vote`" if mcp_prefix else "`vote`"
    stop_name = f"`{mcp_prefix}stop`" if mcp_prefix else "`stop`"

    if "new_answer" in tool_names and "stop" in tool_names:
        parts.append(
            f"\nYou MUST call either {new_answer_name} (to submit/update your work) or {stop_name} "
            "(to signal your subtask is complete) as an MCP tool call. "
            "Your response is incomplete without one of these tool calls.",
        )
    elif "new_answer" in tool_names and "vote" in tool_names:
        parts.append(
            f"\nYou MUST call either {new_answer_name} (to submit your answer) or {vote_name} "
            "(to vote for the best existing answer) as an MCP tool call. "
            "Your response is incomplete without one of these tool calls.",
        )
    elif "new_answer" in tool_names:
        parts.append(f"\nYou MUST call {new_answer_name} as an MCP tool call to submit your answer.")
    elif "vote" in tool_names:
        parts.append(f"\nYou MUST call {vote_name} as an MCP tool call to vote for the best answer.")
    elif "stop" in tool_names:
        parts.append(f"\nYou MUST call {stop_name} as an MCP tool call to signal your subtask is complete.")

    return "\n".join(parts)


def build_workflow_mcp_server_config(
    tools: list[dict[str, Any]],
    specs_dir: str,
) -> dict[str, Any] | None:
    """Build an MCP server config for workflow tools.

    Filters *tools* to workflow tools only, writes specs to disk,
    and returns the MCP server config dict. Returns None if no workflow
    tools are present.

    Args:
        tools: Full list of tool definitions (may include non-workflow tools).
        specs_dir: Directory path to write the specs JSON file into.

    Returns:
        MCP server config dict, or None if no workflow tools.
    """
    from pathlib import Path

    from ..mcp_tools.workflow_tools_server import (
        build_server_config,
        write_workflow_specs,
    )
    from ..tool.workflow_toolkits.base import WORKFLOW_TOOL_NAMES

    workflow_tools = [t for t in tools if t.get("function", {}).get("name") in WORKFLOW_TOOL_NAMES or t.get("name") in WORKFLOW_TOOL_NAMES]
    if not workflow_tools:
        return None

    specs_path = Path(specs_dir) / "workflow_tool_specs.json"
    write_workflow_specs(workflow_tools, specs_path)
    return build_server_config(specs_path)
