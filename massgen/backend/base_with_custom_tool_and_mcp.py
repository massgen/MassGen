"""
Base class with MCP (Model Context Protocol) support.
Provides common MCP functionality for backends that support MCP integration.
Inherits from LLMBackend and adds MCP-specific features.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import mimetypes
import time
import types
import uuid
from abc import abstractmethod
from collections.abc import AsyncGenerator, Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    NamedTuple,
)

if TYPE_CHECKING:
    from massgen.subagent.background_delegate import BackgroundToolDelegate

import httpx

try:
    import logfire

    LOGFIRE_AVAILABLE = True
except ImportError:
    LOGFIRE_AVAILABLE = False

    # Create a no-op context manager when logfire is not available
    class _NoOpLogfire:
        @staticmethod
        def span(*args, **kwargs):
            from contextlib import nullcontext

            return nullcontext()

    logfire = _NoOpLogfire()

from pydantic import BaseModel

from ..filesystem_manager._constants import (
    EVICTED_RESULTS_DIR,
    FRAMEWORK_MCPS,
    TOOL_RESULT_EVICTION_PREVIEW_TOKENS,
    TOOL_RESULT_EVICTION_THRESHOLD_TOKENS,
)
from ..logger_config import get_event_emitter, log_backend_activity, logger
from ..mcp_tools.hooks import GeneralHookManager, HookType
from ..mcp_tools.server_registry import get_auto_discovery_servers, get_registry_info
from ..nlip.schema import (
    NLIPControlField,
    NLIPFormatField,
    NLIPMessageType,
    NLIPRequest,
    NLIPTokenField,
    NLIPToolCall,
)
from ..structured_logging import get_tracer, log_tool_execution, trace_llm_api_call
from ..token_manager.token_manager import ToolExecutionMetric
from ..tool import ToolManager
from ..utils import CoordinationStage
from ..utils.tool_argument_normalization import normalize_json_object_argument
from ._constants import configure_openrouter_extra_body
from .base import LLMBackend, StreamChunk, get_multimodal_tool_definitions
from .capabilities import normalize_backend_type


@dataclass
class ToolExecutionConfig:
    """Configuration for unified tool execution.

    Encapsulates all differences between custom and MCP tool execution,
    enabling unified processing.
    """

    tool_type: str  # "custom" or "mcp" for identification
    chunk_type: str  # "custom_tool_status" or "mcp_status" for StreamChunk type
    emoji_prefix: str  # "🔧 [Custom Tool]" or "🔧 [MCP Tool]" for display
    success_emoji: str  # "✅ [Custom Tool]" or "✅ [MCP Tool]" for completion
    error_emoji: str  # "❌ [Custom Tool Error]" or "❌ [MCP Tool Error]" for errors
    source_prefix: str  # "custom_" or "mcp_" for chunk source field
    status_called: str  # "custom_tool_called" or "mcp_tool_called"
    status_response: str  # "custom_tool_response" or "mcp_tool_response"
    status_error: str  # "custom_tool_error" or "mcp_tool_error"
    execution_callback: Callable  # reference to _execute_custom_tool or _execute_mcp_function_with_retry


@dataclass
class ToolExecutionResult:
    """Container for the outcome of a single tool execution.

    Used by the unified scheduler to keep per-call chunks and message mutations
    isolated from shared state until we're ready to merge them.
    """

    call: dict[str, Any]
    chunks: list[StreamChunk]
    messages: list[dict[str, Any]]
    exception: BaseException | None = None


class UploadFileError(Exception):
    """Raised when an upload specified in configuration fails to process."""


class UnsupportedUploadSourceError(UploadFileError):
    """Raised when a provided upload source cannot be processed (e.g., URL without fetch support)."""


class CustomToolChunk(NamedTuple):
    """Streaming chunk from custom tool execution."""

    data: str  # Chunk data to stream to user
    completed: bool  # True for the last chunk only
    accumulated_result: str  # Final accumulated result (only when completed=True)
    meta_info: dict[str, Any] | None = None  # Multimodal metadata (e.g., from read_media)


class EvictionResult(NamedTuple):
    """Result of attempting to evict a large tool result to file.

    Attributes:
        text: Either the original result text (if not evicted) or a reference
              message with preview (if evicted to file)
        was_evicted: True if result was evicted to file, False if kept in memory
    """

    text: str
    was_evicted: bool


BACKGROUND_TOOL_START_NAME = "custom_tool__start_background_tool"
BACKGROUND_TOOL_STATUS_NAME = "custom_tool__get_background_tool_status"
BACKGROUND_TOOL_RESULT_NAME = "custom_tool__get_background_tool_result"
BACKGROUND_TOOL_CANCEL_NAME = "custom_tool__cancel_background_tool"
BACKGROUND_TOOL_LIST_NAME = "custom_tool__list_background_tools"
BACKGROUND_TOOL_WAIT_NAME = "custom_tool__wait_for_background_tool"
BACKGROUND_TOOL_MANAGEMENT_NAMES = {
    BACKGROUND_TOOL_START_NAME,
    BACKGROUND_TOOL_STATUS_NAME,
    BACKGROUND_TOOL_RESULT_NAME,
    BACKGROUND_TOOL_CANCEL_NAME,
    BACKGROUND_TOOL_LIST_NAME,
    BACKGROUND_TOOL_WAIT_NAME,
}
BACKGROUND_TOOL_TERMINAL_STATUSES = {"completed", "error", "cancelled"}
BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS = 30.0
BACKGROUND_TOOL_WAIT_MAX_TIMEOUT_SECONDS = 600.0
BACKGROUND_TOOL_WAIT_POLL_INTERVAL_SECONDS = 0.2


@dataclass
class BackgroundToolJob:
    """Runtime state for a background tool execution."""

    job_id: str
    tool_name: str
    tool_type: str
    arguments: dict[str, Any]
    status: str
    created_at: float
    source_call_id: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None


class ExecutionContext(BaseModel):
    """Execution context for MCP tool execution."""

    messages: list[dict[str, Any]] = []
    agent_system_message: str | None = None
    agent_id: str | None = None
    backend_name: str | None = None
    backend_type: str | None = None  # Backend type for capability lookup (e.g., "openai", "claude")
    model: str | None = None  # Model name for capability lookup
    current_stage: CoordinationStage | None = None

    # Workspace context for file operations and multimodal tools
    agent_cwd: str | None = None  # Working directory for file operations
    allowed_paths: list[str] | None = None  # Allowed paths for file access
    multimodal_config: dict[str, Any] | None = None  # Multimodal generation config

    # Task context for external API calls (multimodal tools, subagents)
    # Loaded from CONTEXT.md in the workspace
    task_context: str | None = None

    # These will be computed after initialization
    system_messages: list[dict[str, Any]] | None = None
    user_messages: list[dict[str, Any]] | None = None
    prompt: list[dict[str, Any]] | None = None

    def __init__(
        self,
        messages: list[dict[str, Any]] | None = None,
        agent_system_message: str | None = None,
        agent_id: str | None = None,
        backend_name: str | None = None,
        backend_type: str | None = None,
        model: str | None = None,
        current_stage: CoordinationStage | None = None,
        agent_cwd: str | None = None,
        allowed_paths: list[str] | None = None,
        multimodal_config: dict[str, Any] | None = None,
        task_context: str | None = None,
    ):
        """Initialize execution context."""
        super().__init__(
            messages=messages or [],
            agent_system_message=agent_system_message,
            agent_id=agent_id,
            backend_name=backend_name,
            backend_type=backend_type,
            model=model,
            current_stage=current_stage,
            agent_cwd=agent_cwd,
            allowed_paths=allowed_paths,
            multimodal_config=multimodal_config,
            task_context=task_context,
        )
        # Now you can process messages after Pydantic initialization
        self._process_messages()

    def _process_messages(self) -> None:
        """Process messages to extract commonly used fields."""
        if self.messages:
            self.system_messages = []
            self.user_messages = []

            for msg in self.messages:
                role = msg.get("role")

                if role == "system":
                    self.system_messages.append(msg)

                if role == "user":
                    self.user_messages.append(msg)

            if self.current_stage == CoordinationStage.INITIAL_ANSWER:
                self.prompt = [self.exec_instruction()] + self.user_messages
            elif self.current_stage == CoordinationStage.ENFORCEMENT:
                self.prompt = self.user_messages
            elif self.current_stage == CoordinationStage.PRESENTATION:
                if len(self.system_messages) > 1:
                    raise ValueError(
                        "Execution Context expects only one system message during PRESENTATION stage",
                    )
                system_message = self._filter_system_message(self.system_messages[0])
                self.prompt = [system_message] + self.user_messages

    # Todo: Temporary solution. We should change orchestrator not to preprend agent system message
    def _filter_system_message(self, sys_msg):
        """Filter out agent system message prefix from system message content."""
        content = sys_msg.get("content", "")
        # Remove agent_system_message prefix if present
        if self.agent_system_message and isinstance(content, str):
            if content.startswith(self.agent_system_message):
                # Remove the prefix and any following whitespace/newlines
                remaining = content[len(self.agent_system_message) :].lstrip("\n ")
                sys_msg["content"] = remaining

        return sys_msg

    @staticmethod
    def exec_instruction() -> dict:
        instruction = (
            "You MUST digest existing answers, combine their strengths, " "and do additional work to address their weaknesses, " "then generate a better answer to address the ORIGINAL MESSAGE."
        )
        return {"role": "system", "content": instruction}


# MCP integration imports
try:
    from ..mcp_tools import (
        Function,
        MCPCircuitBreaker,
        MCPCircuitBreakerManager,
        MCPClient,
        MCPConfigHelper,
        MCPConnectionError,
        MCPError,
        MCPErrorHandler,
        MCPExecutionManager,
        MCPMessageManager,
        MCPResourceManager,
        MCPServerError,
        MCPSetupManager,
        MCPTimeoutError,
    )
except ImportError as e:
    logger.warning(f"MCP import failed: {e}")
    # Create fallback assignments for all MCP imports
    MCPClient = None
    MCPCircuitBreaker = None
    Function = None
    MCPErrorHandler = None
    MCPSetupManager = None
    MCPResourceManager = None
    MCPExecutionManager = None
    MCPMessageManager = None
    MCPConfigHelper = None
    MCPCircuitBreakerManager = None
    MCPError = ImportError
    MCPConnectionError = ImportError
    MCPTimeoutError = ImportError
    MCPServerError = ImportError

# Supported file types for OpenAI File Search
# NOTE: These are the extensions supported by OpenAI's File Search API.
# Claude Files API has different restrictions (only .pdf and .txt) - see claude.py for Claude-specific validation.
FILE_SEARCH_SUPPORTED_EXTENSIONS = {
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".doc",
    ".docx",
    ".html",
    ".java",
    ".js",
    ".json",
    ".md",
    ".pdf",
    ".php",
    ".pptx",
    ".py",
    ".rb",
    ".sh",
    ".tex",
    ".ts",
    ".txt",
}

FILE_SEARCH_MAX_FILE_SIZE = 512 * 1024 * 1024  # 512 MB
# Max size for media uploads (audio/video). Configurable via `media_max_file_size_mb` in config/all_params.
MEDIA_MAX_FILE_SIZE_MB = 64

# Supported audio formats for OpenAI audio models (starting with wav and mp3)
SUPPORTED_AUDIO_FORMATS = {"mp3", "wav"}

# Supported audio MIME types (for validation consistency)
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
}


class CustomToolAndMCPBackend(LLMBackend):
    """Base backend class with MCP (Model Context Protocol) support."""

    def __init__(self, api_key: str | None = None, **kwargs):
        """Initialize backend with MCP support."""
        super().__init__(api_key, **kwargs)

        # Initialize backend name and agent ID early (needed for logging)
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get("agent_id", None)

        # Custom tools support - initialize before api_params_handler
        self.custom_tool_manager = ToolManager()
        self._custom_tool_names: set[str] = set()
        self._background_tool_jobs: dict[str, BackgroundToolJob] = {}
        self._background_tool_tasks: dict[str, asyncio.Task[Any]] = {}
        self._pending_background_tool_results: list[dict[str, Any]] = []
        self._background_tool_wait_seen_ids: set[str] = set()
        self._background_wait_interrupt_provider: Callable[[str], Any] | None = None
        self._background_tool_delegate: BackgroundToolDelegate | None = None
        self._background_tool_management_names: set[str] = set(
            BACKGROUND_TOOL_MANAGEMENT_NAMES,
        )
        self._custom_tool_names.update(self._background_tool_management_names)

        # Store execution context for custom tool execution
        self._execution_context = None

        # NLIP routing support (injected by agent configuration)
        self._nlip_router = None
        self._nlip_enabled = False

        # Incomplete response recovery tracking
        self._incomplete_response_count = 0
        self._max_incomplete_response_retries = kwargs.get("max_incomplete_response_retries", 5)

        # Register custom tools if provided
        custom_tools = kwargs.get("custom_tools", [])
        if custom_tools:
            self._register_custom_tools(custom_tools)

        # Register multimodal tools if enabled
        enable_multimodal = self.config.get(
            "enable_multimodal_tools",
            False,
        ) or kwargs.get("enable_multimodal_tools", False)
        if enable_multimodal:
            self._register_custom_tools(get_multimodal_tool_definitions())
            logger.info(
                f"[{self.backend_name}] Multimodal tools enabled: read_media, generate_media",
            )

        # Build multimodal config for injection into read_media and generate_media tools
        # Priority: explicit multimodal_config > individual config variables
        self._multimodal_config = self.config.get(
            "multimodal_config",
            {},
        ) or kwargs.get("multimodal_config", {})

        # If not explicitly set, build from individual generation config variables
        if not self._multimodal_config:
            self._multimodal_config = self._build_multimodal_config_from_params()

        # MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])

        # Auto-discovery: Merge registry servers when enabled
        auto_discover = self.config.get(
            "auto_discover_custom_tools",
            False,
        ) or kwargs.get("auto_discover_custom_tools", False)
        if auto_discover:
            registry_servers = get_auto_discovery_servers()
            if registry_servers:
                # Get server names already configured to avoid duplicates
                configured_server_names = {s.get("name") for s in self.mcp_servers if isinstance(s, dict) and "name" in s}

                # Add registry servers that aren't already configured
                added_servers = []
                for registry_server in registry_servers:
                    if registry_server.get("name") not in configured_server_names:
                        self.mcp_servers.append(registry_server)
                        added_servers.append(registry_server.get("name"))

                if added_servers:
                    logger.info(
                        f"[{self.backend_name}] Auto-discovery enabled: Added MCP servers from registry: {', '.join(added_servers)}",
                    )

                    # Log info about unavailable servers
                    registry_info = get_registry_info()
                    if registry_info.get("unavailable_servers"):
                        unavailable = registry_info["unavailable_servers"]
                        missing_keys = registry_info.get("missing_api_keys", {})
                        logger.info(
                            f"[{self.backend_name}] Registry servers not added (missing API keys): {', '.join([f'{s} (needs {missing_keys.get(s)})' for s in unavailable])}",
                        )

        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: MCPClient | None = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_function_names: set[str] = set()

        # Granular tool execution metrics tracking
        self._tool_execution_metrics: list[ToolExecutionMetric] = []
        self._current_round_number: int = 0

        # Circuit breaker for MCP tools (stdio + streamable-http)
        self._mcp_tools_circuit_breaker = None
        self._circuit_breakers_enabled = MCPCircuitBreaker is not None

        # Initialize circuit breaker if available and MCP servers are configured
        if self._circuit_breakers_enabled and self.mcp_servers:
            # Use shared utility to build circuit breaker configuration
            mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools") if MCPConfigHelper else None

            if mcp_tools_config:
                self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
                logger.info("Circuit breaker initialized for MCP tools")
            else:
                logger.warning(
                    "MCP tools circuit breaker config not available, disabling circuit breaker functionality",
                )
                self._circuit_breakers_enabled = False
        else:
            if not self.mcp_servers:
                # No MCP servers configured - skip circuit breaker initialization silently
                self._circuit_breakers_enabled = False
            else:
                logger.warning(
                    "Circuit breakers not available - proceeding without circuit breaker protection",
                )

        # Function registry for mcp_tools-based servers (stdio + streamable-http)
        self._mcp_functions: dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)

        # Initialize backend name and agent ID for MCP operations
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get("agent_id", None)

        # Initialize General Hook Manager for Pre/PostToolUse hooks
        self._general_hook_manager: GeneralHookManager | None = None
        hooks_config = self.config.get("hooks") or kwargs.get("hooks")
        if hooks_config:
            self._general_hook_manager = GeneralHookManager()
            self._general_hook_manager.register_hooks_from_config(
                hooks_config,
                agent_id=self.agent_id,
            )
            logger.info(
                f"[{self.backend_name}] Hook framework initialized for agent {self.agent_id}",
            )

        # Debug delay for testing injection flow
        # When set, adds artificial delay after N tool calls to simulate slow agents
        # This allows other agents to complete and inject updates before this agent continues
        self._debug_delay_seconds: float = self.config.get("debug_delay_seconds", 0.0)
        self._debug_delay_after_n_tools: int = self.config.get("debug_delay_after_n_tools", 3)
        self._debug_tool_call_count: int = 0
        self._debug_delay_applied: bool = False
        if self._debug_delay_seconds > 0:
            logger.info(
                f"[{self.backend_name}] Debug delay enabled: {self._debug_delay_seconds}s after {self._debug_delay_after_n_tools} tool calls for agent {self.agent_id}",
            )

    def set_general_hook_manager(self, manager: GeneralHookManager) -> None:
        """Set the GeneralHookManager (used by orchestrator for global hooks)."""
        self._general_hook_manager = manager

    def set_subagent_spawn_callback(self, callback: Callable[[str, dict[str, Any], str], None]) -> None:
        """Set callback for subagent spawn notifications.

        This callback is invoked (in a background thread) when spawn_subagents is called,
        BEFORE the blocking execution begins. This allows the TUI to show progress immediately.

        Args:
            callback: Function(tool_name, args_dict, call_id) to invoke on spawn
        """
        self._subagent_spawn_callback = callback

    def _build_multimodal_config_from_params(self) -> dict[str, Any]:
        """Build multimodal_config from individual generation config variables.

        Reads the following config variables and builds a structured config:
        - image_generation_backend, image_generation_model
        - video_generation_backend, video_generation_model
        - audio_generation_backend, audio_generation_model

        Returns:
            Dict with structure: {"image": {"backend": ..., "model": ...}, ...}
        """
        multimodal_config: dict[str, Any] = {}

        # Image generation config
        image_backend = self.config.get("image_generation_backend")
        image_model = self.config.get("image_generation_model")
        if image_backend or image_model:
            multimodal_config["image"] = {}
            if image_backend:
                multimodal_config["image"]["backend"] = image_backend
            if image_model:
                multimodal_config["image"]["model"] = image_model

        # Video generation config
        video_backend = self.config.get("video_generation_backend")
        video_model = self.config.get("video_generation_model")
        if video_backend or video_model:
            multimodal_config["video"] = {}
            if video_backend:
                multimodal_config["video"]["backend"] = video_backend
            if video_model:
                multimodal_config["video"]["model"] = video_model

        # Audio generation config
        audio_backend = self.config.get("audio_generation_backend")
        audio_model = self.config.get("audio_generation_model")
        if audio_backend or audio_model:
            multimodal_config["audio"] = {}
            if audio_backend:
                multimodal_config["audio"]["backend"] = audio_backend
            if audio_model:
                multimodal_config["audio"]["model"] = audio_model

        if multimodal_config:
            logger.debug(
                f"[{self.backend_name}] Built multimodal_config from params: {multimodal_config}",
            )

        return multimodal_config

    def reset_incomplete_response_count(self) -> None:
        """Reset the incomplete response recovery counter.

        Should be called after a successful stream completion to reset
        the counter for the next streaming operation.
        """
        if self._incomplete_response_count > 0:
            logger.debug(
                f"[{self.backend_name}] Resetting incomplete response count from {self._incomplete_response_count}",
            )
        self._incomplete_response_count = 0

    def set_nlip_router(self, nlip_router, enabled: bool = True) -> None:
        """
        Inject NLIP router for optional standardized tool communication.

        Args:
            nlip_router: NLIPRouter instance from agent config
            enabled: Whether to use NLIP routing (default: True)
        """
        self._nlip_router = nlip_router
        self._nlip_enabled = enabled
        logger.info(f"[NLIP] Router injected, enabled={enabled}")

    def set_round_number(self, round_number: int) -> None:
        """Set the current round number for tool metrics tracking."""
        self._current_round_number = round_number

    def get_tool_metrics(self) -> list[dict[str, Any]]:
        """Get all tool execution metrics as list of dicts."""
        return [m.to_dict() for m in self._tool_execution_metrics]

    def get_tool_metrics_summary(self) -> dict[str, Any]:
        """Get aggregated tool metrics summary with distribution statistics.

        Returns:
            Dictionary with total counts, per-tool breakdown, and distribution stats.
        """
        if not self._tool_execution_metrics:
            return {
                "total_calls": 0,
                "total_failures": 0,
                "total_execution_time_ms": 0,
                "by_tool": {},
            }

        by_tool: dict[str, dict[str, Any]] = {}
        total_failures = 0
        total_time_ms = 0.0

        # First pass: collect all values per tool for distribution calculation
        tool_input_chars: dict[str, list[int]] = {}
        tool_output_chars: dict[str, list[int]] = {}
        tool_exec_times: dict[str, list[float]] = {}

        for m in self._tool_execution_metrics:
            name = m.tool_name
            if name not in by_tool:
                by_tool[name] = {
                    "call_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "total_execution_time_ms": 0.0,
                    "total_input_chars": 0,
                    "total_output_chars": 0,
                    "tool_type": m.tool_type,
                }
                tool_input_chars[name] = []
                tool_output_chars[name] = []
                tool_exec_times[name] = []

            by_tool[name]["call_count"] += 1
            if m.success:
                by_tool[name]["success_count"] += 1
            else:
                by_tool[name]["failure_count"] += 1
                total_failures += 1
            by_tool[name]["total_execution_time_ms"] += m.execution_time_ms
            by_tool[name]["total_input_chars"] += m.input_chars
            by_tool[name]["total_output_chars"] += m.output_chars
            total_time_ms += m.execution_time_ms

            # Collect individual values for distribution
            tool_input_chars[name].append(m.input_chars)
            tool_output_chars[name].append(m.output_chars)
            tool_exec_times[name].append(m.execution_time_ms)

        # Calculate averages and distribution stats
        for name, tool_stats in by_tool.items():
            count = tool_stats["call_count"]
            if count > 0:
                # Existing averages
                tool_stats["avg_execution_time_ms"] = round(
                    tool_stats["total_execution_time_ms"] / count,
                    2,
                )
                tool_stats["input_tokens_est"] = tool_stats["total_input_chars"] // 4
                tool_stats["output_tokens_est"] = tool_stats["total_output_chars"] // 4

                # New: per-call averages
                tool_stats["avg_input_chars"] = round(tool_stats["total_input_chars"] / count, 1)
                tool_stats["avg_output_chars"] = round(tool_stats["total_output_chars"] / count, 1)

                # New: distribution stats for output (the bottleneck concern)
                output_vals = sorted(tool_output_chars[name])
                tool_stats["output_distribution"] = {
                    "min": output_vals[0],
                    "max": output_vals[-1],
                    "median": output_vals[len(output_vals) // 2],
                    "p90": output_vals[int(len(output_vals) * 0.9)] if count >= 10 else output_vals[-1],
                    "p99": output_vals[int(len(output_vals) * 0.99)] if count >= 100 else output_vals[-1],
                }

                # New: distribution stats for input
                input_vals = sorted(tool_input_chars[name])
                tool_stats["input_distribution"] = {
                    "min": input_vals[0],
                    "max": input_vals[-1],
                    "median": input_vals[len(input_vals) // 2],
                }

                # New: execution time distribution
                exec_vals = sorted(tool_exec_times[name])
                tool_stats["exec_time_distribution"] = {
                    "min_ms": round(exec_vals[0], 2),
                    "max_ms": round(exec_vals[-1], 2),
                    "median_ms": round(exec_vals[len(exec_vals) // 2], 2),
                    "p90_ms": round(exec_vals[int(len(exec_vals) * 0.9)], 2) if count >= 10 else round(exec_vals[-1], 2),
                }

        return {
            "total_calls": len(self._tool_execution_metrics),
            "total_failures": total_failures,
            "total_execution_time_ms": round(total_time_ms, 2),
            "by_tool": by_tool,
        }

    def _backend_call_to_nlip(self, call: dict[str, Any]) -> NLIPToolCall | None:
        """
        Convert backend tool call format to NLIP format with validation.

        Args:
            call: Backend format {"call_id", "name", "arguments"}

        Returns:
            NLIPToolCall or None if conversion fails
        """
        try:
            # Validate required fields
            call_id = call.get("call_id", "")
            name = call.get("name", "")
            if not call_id:
                logger.error(f"[NLIP] Missing call_id in backend call: {call}")
                return None
            if not name:
                logger.error(f"[NLIP] Missing name in backend call: {call}")
                return None

            # Parse arguments (handle dict, JSON string, and double-encoded JSON string).
            args_raw = call.get("arguments", "{}")
            try:
                args, decode_passes = normalize_json_object_argument(
                    args_raw,
                    field_name="arguments",
                )
            except ValueError as exc:
                snippet = args_raw[:200] + "..." if isinstance(args_raw, str) and len(args_raw) > 200 else str(args_raw)
                logger.error(
                    f"[NLIP] Failed to parse arguments for {name}: {exc}. " f"Invalid JSON (truncated): {snippet}",
                )
                return None
            if decode_passes > 1:
                logger.info(
                    "[NLIP] Normalized %s decode passes for %s arguments",
                    decode_passes,
                    name,
                )

            return NLIPToolCall(
                tool_id=call_id,
                tool_name=name,
                parameters=args,
                require_confirmation=False,
            )
        except Exception as exc:
            logger.error(f"[NLIP] Conversion failed: {exc}")
            return None

    def _build_nlip_request(self, call: dict[str, Any]) -> NLIPRequest:
        """Construct an NLIP request payload for a backend tool call."""
        if not self._nlip_router:
            raise RuntimeError("NLIP router is not configured")

        # Inject agent_cwd into arguments (same as standard path)
        original_args = call.get("arguments", "{}")
        arguments = self._parse_tool_arguments(original_args)
        if self.filesystem_manager and self.filesystem_manager.cwd:
            if "agent_cwd" not in arguments or arguments.get("agent_cwd") is None:
                arguments["agent_cwd"] = self.filesystem_manager.cwd
                logger.debug(
                    f"[NLIP] Injected agent_cwd: {self.filesystem_manager.cwd}",
                )

        call_with_cwd = call.copy()
        call_with_cwd["arguments"] = json.dumps(arguments) if isinstance(original_args, str) else arguments

        nlip_call = self._backend_call_to_nlip(call_with_cwd)
        if not nlip_call:
            raise ValueError("Failed to convert call to NLIP format")

        execution_context: dict[str, Any] = {}
        if getattr(self, "_execution_context", None):
            try:
                execution_context = self._execution_context.model_dump()
            except Exception as exc:
                logger.warning(f"[NLIP] Failed to serialize execution context: {exc}")
        else:
            logger.debug(
                "[NLIP] No execution context available when building NLIP request",
            )

        if self.filesystem_manager:
            execution_context["filesystem"] = {
                "cwd": getattr(self.filesystem_manager, "cwd", None),
                "allowed_paths": getattr(self.filesystem_manager, "allowed_paths", []),
            }

        return NLIPRequest(
            format=NLIPFormatField(
                content_type="application/json",
                schema_version="1.0",
            ),
            control=NLIPControlField(
                message_type=NLIPMessageType.REQUEST,
                message_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow().isoformat() + "Z",
                timeout=300,
            ),
            token=NLIPTokenField(
                session_id=f"backend_{id(self)}_{call.get('call_id')}",
                conversation_turn=0,
            ),
            content={
                "backend_execution": True,
                "execution_context": execution_context,
            },
            tool_calls=[nlip_call],
        )

    def supports_upload_files(self) -> bool:
        """Return True if the backend supports `upload_files` preprocessing."""
        return False

    @abstractmethod
    async def _process_stream(
        self,
        stream,
        all_params,
        agent_id: str | None = None,
    ) -> AsyncGenerator[StreamChunk]:
        """Process stream."""
        yield StreamChunk(type="error", error="Not implemented")

    # Custom tools support
    def _register_custom_tools(self, custom_tools: list[dict[str, Any]]) -> None:
        """Register custom tools with the tool manager.

        Supports flexible configuration:
        - function: str | List[str]
        - description: str (shared) | List[str] (1-to-1 mapping)
        - preset_args: dict (shared) | List[dict] (1-to-1 mapping)

        Examples:
            # Single function
            function: "my_func"
            description: "My description"

            # Multiple functions with shared description
            function: ["func1", "func2"]
            description: "Shared description"

            # Multiple functions with individual descriptions
            function: ["func1", "func2"]
            description: ["Description 1", "Description 2"]

            # Multiple functions with mixed (shared desc, individual args)
            function: ["func1", "func2"]
            description: "Shared description"
            preset_args: [{"arg1": "val1"}, {"arg1": "val2"}]

        Args:
            custom_tools: List of custom tool configurations
        """
        # Collect unique categories and create them if needed
        categories = set()
        for tool_config in custom_tools:
            if isinstance(tool_config, dict):
                category = tool_config.get("category", "default")
                if category != "default":
                    categories.add(category)

        # Create categories that don't exist
        for category in categories:
            if category not in self.custom_tool_manager.tool_categories:
                self.custom_tool_manager.setup_category(
                    category_name=category,
                    description=f"Custom {category} tools",
                    enabled=True,
                )

        # Register each custom tool
        for tool_config in custom_tools:
            try:
                if isinstance(tool_config, dict):
                    # Extract base configuration
                    path = tool_config.get("path")
                    category = tool_config.get("category", "default")

                    # Normalize function field to list (support both "function" and "func" keys)
                    func_field = tool_config.get("function") or tool_config.get("func")
                    if isinstance(func_field, str):
                        functions = [func_field]
                    elif isinstance(func_field, list):
                        functions = func_field
                    elif callable(func_field):
                        # Direct function object passed
                        functions = [func_field]
                    else:
                        logger.error(
                            f"Invalid function field type: {type(func_field)}. " f"Must be str, callable, or List[str].",
                        )
                        continue

                    if not functions:
                        logger.error("Empty function list in tool config")
                        continue

                    num_functions = len(functions)

                    # Process name field (can be str or List[str])
                    name_field = tool_config.get("name")
                    names = self._process_field_for_functions(
                        name_field,
                        num_functions,
                        "name",
                    )
                    if names is None:
                        continue  # Validation error, skip this tool

                    # Process description field (can be str or List[str])
                    desc_field = tool_config.get("description")
                    descriptions = self._process_field_for_functions(
                        desc_field,
                        num_functions,
                        "description",
                    )
                    if descriptions is None:
                        continue  # Validation error, skip this tool

                    # Process preset_args field (can be dict or List[dict])
                    preset_field = tool_config.get("preset_args")
                    preset_args_list = self._process_field_for_functions(
                        preset_field,
                        num_functions,
                        "preset_args",
                    )
                    if preset_args_list is None:
                        continue  # Validation error, skip this tool

                    # Register each function with its corresponding values
                    for i, func in enumerate(functions):
                        # Inject agent_cwd into preset_args if filesystem_manager is available
                        final_preset_args = preset_args_list[i].copy() if preset_args_list[i] else {}
                        if self.filesystem_manager and self.filesystem_manager.cwd:
                            final_preset_args["agent_cwd"] = self.filesystem_manager.cwd
                            logger.info(
                                f"Injecting agent_cwd for {func}: {self.filesystem_manager.cwd}",
                            )
                        elif self.filesystem_manager:
                            logger.warning(
                                f"filesystem_manager exists but cwd is None for {func}",
                            )
                        else:
                            logger.warning(
                                f"No filesystem_manager available for {func}",
                            )

                        # Load the function first if custom name is needed
                        if names[i] and names[i] != func:
                            # Load function to apply custom name
                            if path:
                                loaded_func = self.custom_tool_manager._load_function_from_path(
                                    path,
                                    func,
                                )
                            else:
                                loaded_func = self.custom_tool_manager._load_builtin_function(
                                    func,
                                )

                            if loaded_func is None:
                                logger.error(
                                    f"Could not load function '{func}' from path: {path}",
                                )
                                continue

                            loaded_func.__name__ = names[i]

                            # Register with loaded function (no path needed)
                            self.custom_tool_manager.add_tool_function(
                                path=None,
                                func=loaded_func,
                                category=category,
                                preset_args=final_preset_args,
                                description=descriptions[i],
                            )
                        else:
                            # No custom name or same as function name, use normal registration
                            self.custom_tool_manager.add_tool_function(
                                path=path,
                                func=func,
                                category=category,
                                preset_args=final_preset_args,
                                description=descriptions[i],
                            )

                        # Use custom name for logging and tracking if provided
                        # Handle callable functions by extracting their __name__
                        if names[i]:
                            registered_name = names[i]
                        elif callable(func):
                            registered_name = getattr(func, "__name__", str(func))
                        else:
                            registered_name = str(func)

                        # Track tool name for categorization
                        if registered_name.startswith("custom_tool__"):
                            self._custom_tool_names.add(registered_name)
                        else:
                            self._custom_tool_names.add(
                                f"custom_tool__{registered_name}",
                            )

                        logger.info(
                            f"Registered custom tool: {registered_name} from {path} " f"(category: {category}, " f"desc: '{descriptions[i][:50] if descriptions[i] else 'None'}...')",
                        )

            except Exception as e:
                func_name = tool_config.get("function", "unknown")
                logger.error(
                    f"Failed to register custom tool {func_name}: {e}",
                    exc_info=True,
                )

    def _process_field_for_functions(
        self,
        field_value: Any,
        num_functions: int,
        field_name: str,
    ) -> list[Any] | None:
        """Process a config field that can be a single value or list.

        Conversion rules:
        - None → [None, None, ...] (repeated num_functions times)
        - Single value (not list) → [value, value, ...] (shared)
        - List with matching length → use as-is (1-to-1 mapping)
        - List with wrong length → ERROR (return None)

        Args:
            field_value: The field value from config
            num_functions: Number of functions being registered
            field_name: Name of the field (for error messages)

        Returns:
            List of values (one per function), or None if validation fails

        Examples:
            _process_field_for_functions(None, 3, "desc")
            → [None, None, None]

            _process_field_for_functions("shared", 3, "desc")
            → ["shared", "shared", "shared"]

            _process_field_for_functions(["a", "b", "c"], 3, "desc")
            → ["a", "b", "c"]

            _process_field_for_functions(["a", "b"], 3, "desc")
            → None (error logged)
        """
        # Case 1: None or missing field → use None for all functions
        if field_value is None:
            return [None] * num_functions

        # Case 2: Single value (not a list) → share across all functions
        if not isinstance(field_value, list):
            return [field_value] * num_functions

        # Case 3: List value → must match function count exactly
        if len(field_value) == num_functions:
            return field_value
        else:
            # Length mismatch → validation error
            logger.error(
                f"Configuration error: {field_name} is a list with "
                f"{len(field_value)} items, but there are {num_functions} functions. "
                f"Either use a single value (shared) or a list with exactly "
                f"{num_functions} items (1-to-1 mapping).",
            )
            return None

    async def _stream_execution_results(
        self,
        tool_request: dict[str, Any],
    ) -> AsyncGenerator[tuple[str, bool, dict[str, Any] | None]]:
        """Stream execution results from tool manager, yielding (data, is_log, meta_info) tuples.

        Args:
            tool_request: Tool request dictionary with name and input

        Yields:
            Tuple of (data: str, is_log: bool, meta_info: Optional[Dict]) for each result block.
            The meta_info contains multimodal data (e.g., from read_media tool).
        """
        try:
            async for result in self.custom_tool_manager.execute_tool(
                tool_request,
                execution_context=self._execution_context.model_dump(),
            ):
                is_log = getattr(result, "is_log", False)
                meta_info = getattr(result, "meta_info", None)

                if hasattr(result, "output_blocks"):
                    for block in result.output_blocks:
                        data = ""
                        if hasattr(block, "data"):
                            data = str(block.data)

                        if data:
                            yield (data, is_log, meta_info)

        except Exception as e:
            logger.error(f"Error in custom tool execution: {e}")
            yield (f"Error: {str(e)}", True, None)

    async def stream_custom_tool_execution(
        self,
        call: dict[str, Any],
        agent_id_override: str | None = None,
    ) -> AsyncGenerator[CustomToolChunk]:
        """Stream custom tool execution with differentiation between logs and final results.

        This method:
        - Streams all results (logs and final) to users in real-time
        - Accumulates only is_log=False results for message history
        - Yields CustomToolChunk with completed=False for intermediate results
        - Yields final CustomToolChunk with completed=True and accumulated result

        Args:
            call: Function call dictionary with name and arguments
            agent_id_override: Explicit agent ID for broadcast tools. Use this to avoid race
                conditions when multiple agents run concurrently (shared _execution_context
                can get overwritten). If not provided, falls back to _execution_context.

        Yields:
            CustomToolChunk instances for streaming to user
        """
        import json

        tool_name = call.get("name", "")

        # Internal background-management tools are handled directly here
        # (they are schemas-only and not registered in ToolManager).
        # Normalize MCP-prefixed names so the dispatcher matches correctly.
        if self._is_background_management_tool(tool_name):
            bg_tool_name = tool_name
            _massgen_prefix = "mcp__massgen_custom_tools__"
            if bg_tool_name.startswith(_massgen_prefix):
                bg_tool_name = bg_tool_name[len(_massgen_prefix) :]
            try:
                parsed_arguments = self._parse_tool_arguments(call.get("arguments", "{}"))
            except Exception as e:  # noqa: BLE001
                result_payload = {
                    "success": False,
                    "error": f"Invalid arguments: {e}",
                }
            else:
                result_payload = await self._execute_background_management_tool(
                    bg_tool_name,
                    parsed_arguments,
                    source_call_id=str(call.get("call_id", "") or ""),
                )

            result_text = json.dumps(result_payload, ensure_ascii=False)
            yield CustomToolChunk(
                data="",
                completed=True,
                accumulated_result=result_text,
            )
            return

        # Check if this is a broadcast tool - handle specially
        if tool_name in (
            "ask_others",
            "respond_to_broadcast",
            "check_broadcast_status",
            "get_broadcast_responses",
        ) and hasattr(self, "_broadcast_toolkit"):
            # Parse arguments
            arguments = call["arguments"] if isinstance(call["arguments"], str) else json.dumps(call["arguments"])
            # Use explicit agent_id if provided, then instance agent_id, then execution context
            # Priority: agent_id_override > self.agent_id > _execution_context
            # This avoids race conditions when multiple agents run concurrently
            # (the shared _execution_context can get overwritten by other agents)
            if agent_id_override:
                agent_id = agent_id_override
            elif self.agent_id:
                agent_id = self.agent_id
            else:
                agent_id = self._execution_context.agent_id if self._execution_context and self._execution_context.agent_id else "unknown"

            # Call broadcast toolkit method
            try:
                if tool_name == "ask_others":
                    result = await self._broadcast_toolkit.execute_ask_others(
                        arguments,
                        agent_id,
                    )
                elif tool_name == "respond_to_broadcast":
                    result = await self._broadcast_toolkit.execute_respond_to_broadcast(
                        arguments,
                        agent_id,
                    )
                elif tool_name == "check_broadcast_status":
                    result = await self._broadcast_toolkit.execute_check_broadcast_status(
                        arguments,
                        agent_id,
                    )
                elif tool_name == "get_broadcast_responses":
                    result = await self._broadcast_toolkit.execute_get_broadcast_responses(
                        arguments,
                        agent_id,
                    )

                # Yield final result
                yield CustomToolChunk(
                    data=result,
                    completed=True,
                    accumulated_result=result,
                )
                return
            except Exception as e:
                error_result = json.dumps({"error": str(e), "status": "error"})
                yield CustomToolChunk(
                    data=error_result,
                    completed=True,
                    accumulated_result=error_result,
                )
                return

        # Parse arguments for regular custom tools.
        arguments = self._parse_tool_arguments(call.get("arguments", "{}"))

        # Ensure agent_cwd is always injected if filesystem_manager is available
        # This provides a fallback in case preset_args didn't work during registration
        if self.filesystem_manager and self.filesystem_manager.cwd:
            if "agent_cwd" not in arguments or arguments.get("agent_cwd") is None:
                arguments["agent_cwd"] = self.filesystem_manager.cwd
                logger.info(
                    f"Dynamically injected agent_cwd at execution time: {self.filesystem_manager.cwd}",
                )

        # Inject multimodal_config if available (for read_media tool)
        if hasattr(self, "_multimodal_config") and self._multimodal_config:
            if "multimodal_config" not in arguments:
                arguments["multimodal_config"] = self._multimodal_config
                logger.debug(f"Injected multimodal_config: {self._multimodal_config}")

        tool_request = {
            "name": call["name"],
            "input": arguments,
        }

        accumulated_result = ""
        accumulated_meta_info: dict[str, Any] | None = None

        # Stream all results and accumulate only is_log=True
        async for data, is_log, meta_info in self._stream_execution_results(
            tool_request,
        ):
            # Yield streaming chunk to user
            yield CustomToolChunk(
                data=data,
                completed=False,
                accumulated_result="",
            )

            # Accumulate only final results for message history
            if not is_log:
                accumulated_result += data
                # Capture meta_info from non-log results (e.g., multimodal_inject from read_media)
                if meta_info:
                    accumulated_meta_info = meta_info

        # Yield final chunk with accumulated result and metadata
        yield CustomToolChunk(
            data="",
            completed=True,
            accumulated_result=accumulated_result or "Tool executed successfully",
            meta_info=accumulated_meta_info,
        )

    def _get_custom_tools_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI-formatted schemas for all registered custom tools."""
        schemas = self.custom_tool_manager.fetch_tool_schemas()
        schemas.extend(self._get_background_tool_management_schemas())
        return schemas

    @staticmethod
    def _build_background_management_schema(
        name: str,
        description: str,
        properties: dict[str, Any],
        required: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an OpenAI function schema for an internal background tool."""
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                },
            },
        }

    def _get_background_tool_management_schemas(self) -> list[dict[str, Any]]:
        """Schemas for internal background-tool management helpers."""
        return [
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_START_NAME,
                description=(
                    "Start any custom or MCP tool in the background and return a job_id "
                    "for polling or cancellation. You can provide target arguments via "
                    "`arguments` (or `args`), or pass them as top-level fields."
                ),
                properties={
                    "tool_name": {
                        "type": "string",
                        "description": "Exact tool name to run (custom_tool__* or mcp__*).",
                    },
                    "tool": {
                        "type": "string",
                        "description": "Alias for tool_name.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Arguments for the target tool.",
                        "default": {},
                    },
                    "args": {
                        "type": "object",
                        "description": "Alias for arguments.",
                        "default": {},
                    },
                },
                required=[],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_STATUS_NAME,
                description="Get lightweight status for a background tool job.",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Background job identifier returned by start_background_tool.",
                    },
                },
                required=["job_id"],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_RESULT_NAME,
                description="Get the current or final result payload for a background tool job.",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Background job identifier returned by start_background_tool.",
                    },
                },
                required=["job_id"],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_WAIT_NAME,
                description=("Block until the next unseen background tool job reaches a terminal " "state or the timeout elapses."),
                properties={
                    "timeout_seconds": {
                        "type": "number",
                        "description": ("Maximum seconds to wait for a completed background job. " "Default: 30."),
                        "default": BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS,
                    },
                },
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_CANCEL_NAME,
                description="Cancel a running background tool job.",
                properties={
                    "job_id": {
                        "type": "string",
                        "description": "Background job identifier returned by start_background_tool.",
                    },
                },
                required=["job_id"],
            ),
            self._build_background_management_schema(
                name=BACKGROUND_TOOL_LIST_NAME,
                description=("List background tool jobs. By default returns only currently running jobs; " "set include_all=true to include completed/error/cancelled history."),
                properties={
                    "include_all": {
                        "type": "boolean",
                        "description": "Include terminal jobs (completed/error/cancelled). Default false.",
                        "default": False,
                    },
                },
            ),
        ]

    @staticmethod
    def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
        """Parse tool arguments into a dictionary."""
        parsed, decode_passes = normalize_json_object_argument(
            arguments,
            field_name="arguments",
        )
        if decode_passes > 1:
            logger.info(
                "[ToolArgs] Normalized %s decode passes for tool arguments",
                decode_passes,
            )
        return parsed

    def _is_background_management_tool(self, tool_name: str) -> bool:
        """Return whether a tool name is one of the internal background helpers.

        Handles both direct names (``custom_tool__list_background_tools``) and
        MCP-prefixed variants
        (``mcp__massgen_custom_tools__custom_tool__list_background_tools``) so
        the backend intercepts background management calls regardless of whether
        ``enable_code_based_tools`` is on.
        """
        normalized = (tool_name or "").strip()
        massgen_prefix = "mcp__massgen_custom_tools__"
        if normalized.startswith(massgen_prefix):
            normalized = normalized[len(massgen_prefix) :]
        return normalized in self._background_tool_management_names

    def _resolve_background_tool_type(self, tool_name: str) -> str | None:
        """Resolve the execution type for a background target tool."""
        if not tool_name:
            return None
        if tool_name in {"new_answer", "vote", "stop"}:
            return None
        if self._is_background_management_tool(tool_name):
            return None
        if tool_name in self._custom_tool_names:
            return "custom"
        if tool_name in self._mcp_functions:
            return "mcp"
        return None

    @staticmethod
    def _is_subagent_spawn_target_tool(tool_name: str) -> bool:
        """Return True when target tool resolves to subagent spawning."""
        normalized = str(tool_name or "").strip().lower()
        return "spawn_subagent" in normalized and "subagent" in normalized

    @staticmethod
    def _normalize_subagent_spawn_background_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        """Force wrapped subagent spawn arguments into background mode."""
        normalized = dict(arguments)
        normalized["background"] = True
        normalized.pop("run_in_background", None)
        mode = normalized.get("mode")
        if not (isinstance(mode, str) and mode.lower() == "background"):
            normalized.pop("mode", None)
        return normalized

    @staticmethod
    def _parse_json_or_python_dict(raw_text: str) -> dict[str, Any] | None:
        """Parse dictionary payloads from JSON or Python repr text."""
        if not isinstance(raw_text, str):
            return None
        text = raw_text.strip()
        if not text:
            return None

        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _looks_like_json_payload(raw_text: str) -> bool:
        stripped = str(raw_text or "").lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    @classmethod
    def _annotate_custom_tool_outcome_from_payload(
        cls,
        payload: dict[str, Any],
        *,
        ready: bool,
    ) -> None:
        """Attach tool-level outcome fields for terminal custom-tool jobs."""
        if not ready or payload.get("tool_type") != "custom":
            return

        status = str(payload.get("status") or "")
        if status in {"error", "cancelled"}:
            payload["tool_success"] = False
            payload["tool_error"] = str(payload.get("error") or "Custom tool execution failed")
            return

        if status != "completed":
            payload["tool_success"] = None
            return

        raw_result = str(payload.get("result") or "").strip()
        if not raw_result:
            payload["tool_success"] = False
            payload["tool_error"] = "No final result payload captured from custom tool execution"
            return

        parsed = cls._parse_json_or_python_dict(raw_result)
        if parsed is not None:
            parsed_success = parsed.get("success")
            if isinstance(parsed_success, bool):
                payload["tool_success"] = parsed_success
                if not parsed_success:
                    parsed_error = parsed.get("error")
                    payload["tool_error"] = str(parsed_error) if parsed_error is not None else "Custom tool reported success=false"
            else:
                payload["tool_success"] = True
            return

        if raw_result.startswith("Error:"):
            payload["tool_success"] = False
            payload["tool_error"] = raw_result
            return

        if cls._looks_like_json_payload(raw_result):
            payload["tool_success"] = None
            payload["result_parse_error"] = "Could not parse custom tool JSON result payload"
            return

        payload["tool_success"] = True

    def _mcp_tool_declares_argument(self, tool_name: str, argument_name: str) -> bool:
        """Return True when an MCP tool schema explicitly declares an argument."""
        function = self._mcp_functions.get(tool_name)
        if not function:
            return False
        parameters = getattr(function, "parameters", None)
        if not isinstance(parameters, dict):
            return False
        properties = parameters.get("properties")
        if not isinstance(properties, dict):
            return False
        return argument_name in properties

    def _strip_background_control_args(
        self,
        arguments: dict[str, Any],
        *,
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        """Remove synthetic background control flags before dispatching tools."""
        cleaned = dict(arguments)
        preserve_background = bool(tool_name) and self._mcp_tool_declares_argument(tool_name, "background")
        preserve_run_in_background = bool(tool_name) and self._mcp_tool_declares_argument(tool_name, "run_in_background")
        preserve_mode = bool(tool_name) and self._mcp_tool_declares_argument(tool_name, "mode")

        if not preserve_background and isinstance(cleaned.get("background"), bool):
            cleaned.pop("background", None)
        if not preserve_run_in_background and isinstance(cleaned.get("run_in_background"), bool):
            cleaned.pop("run_in_background", None)
        mode = cleaned.get("mode")
        if not preserve_mode and isinstance(mode, str) and mode.lower() in {"background"}:
            cleaned.pop("mode", None)
        return cleaned

    @staticmethod
    def _is_default_media_background_tool(tool_name: str) -> bool:
        """Return True for media tools that should default to background execution."""
        normalized = (tool_name or "").strip()
        massgen_prefix = "mcp__massgen_custom_tools__"
        if normalized.startswith(massgen_prefix):
            normalized = normalized[len(massgen_prefix) :]
        return normalized in {
            "read_media",
            "generate_media",
            "custom_tool__read_media",
            "custom_tool__generate_media",
        }

    @staticmethod
    def _is_explicit_foreground_request(arguments: dict[str, Any]) -> bool:
        """Return True when args explicitly request foreground/blocking behavior."""
        if arguments.get("background") is False:
            return True
        if arguments.get("run_in_background") is False:
            return True
        return False

    def _should_auto_background_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        """Return True when this call should run in background mode automatically."""
        if self._is_background_management_tool(tool_name):
            return False
        if tool_name in {"new_answer", "vote", "stop"}:
            return False
        if not isinstance(arguments, dict):
            return False

        if self._is_explicit_foreground_request(arguments):
            return False
        if self._is_default_media_background_tool(tool_name):
            return True

        # If the target MCP tool natively defines background controls, let that
        # tool own the semantics instead of wrapping it as a framework background
        # job (for example spawn_subagents(background=True)).
        if self._mcp_tool_declares_argument(tool_name, "background") or self._mcp_tool_declares_argument(tool_name, "run_in_background") or self._mcp_tool_declares_argument(tool_name, "mode"):
            return False

        mode = arguments.get("mode")
        mode_is_background = isinstance(mode, str) and mode.lower() in {"background"}
        return arguments.get("background") is True or mode_is_background

    def _validate_background_tool_prerequisites(self, tool_name: str) -> None:
        """Validate required prerequisites before starting a background tool."""
        if not self._is_default_media_background_tool(tool_name):
            return

        workspace_path: str | None = None
        if self.filesystem_manager and getattr(self.filesystem_manager, "cwd", None):
            workspace_path = str(self.filesystem_manager.cwd)

        try:
            from massgen.context.task_context import TaskContextError, load_task_context

            load_task_context(workspace_path, required=True)
        except TaskContextError as exc:
            raise ValueError(
                f"CONTEXT.md must be created before starting {tool_name} in background. {exc}",
            ) from exc

    @staticmethod
    def _format_unix_timestamp(timestamp: float | None) -> str | None:
        """Convert unix timestamp to ISO string."""
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp).isoformat()

    def _serialize_background_job(
        self,
        job: BackgroundToolJob,
        include_result: bool = False,
    ) -> dict[str, Any]:
        """Serialize background job state for tool responses and hook injection."""
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "tool_name": job.tool_name,
            "tool_type": job.tool_type,
            "status": job.status,
            "created_at": self._format_unix_timestamp(job.created_at),
            "started_at": self._format_unix_timestamp(job.started_at),
            "completed_at": self._format_unix_timestamp(job.completed_at),
            "source_call_id": job.source_call_id,
        }
        if include_result and job.result is not None:
            payload["result"] = job.result
        if job.error:
            payload["error"] = job.error
        return payload

    def _enqueue_completed_background_job(self, job: BackgroundToolJob) -> None:
        """Store completed job payload for post-tool hook injection."""
        self._pending_background_tool_results.append(
            self._serialize_background_job(job, include_result=True),
        )

    def get_pending_background_tool_results(self) -> list[dict[str, Any]]:
        """Return and clear completed background job payloads pending injection."""
        pending = list(self._pending_background_tool_results)
        self._pending_background_tool_results.clear()
        return pending

    def _pop_next_pending_background_tool_result(self) -> dict[str, Any] | None:
        """Pop one completed background job payload from the shared delivery queue."""
        if not self._pending_background_tool_results:
            return None
        return self._pending_background_tool_results.pop(0)

    def register_background_delegate(self, delegate: BackgroundToolDelegate) -> None:
        """Register a delegate that extends background tool management with external job types.

        The delegate is consulted by the 6 background tool handler methods for IDs
        that are not native background tool jobs (e.g., subagent IDs).
        """
        self._background_tool_delegate = delegate

    def set_background_wait_interrupt_provider(
        self,
        provider: Callable[[str], Any] | None,
    ) -> None:
        """Set an optional provider used to interrupt wait_for_background_tool.

        The provider receives the agent ID and may return a dict with:
        - interrupt_reason: str
        - injected_content: str
        """
        self._background_wait_interrupt_provider = provider

    async def _get_background_wait_interrupt_payload(self) -> dict[str, Any] | None:
        """Return normalized wait interrupt payload, if any."""
        if not self._background_wait_interrupt_provider:
            return None

        agent_id = str(self.agent_id or "unknown")
        try:
            payload = self._background_wait_interrupt_provider(agent_id)
            if asyncio.iscoroutine(payload):
                payload = await payload
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[BackgroundTools] Wait interrupt provider failed for %s: %s",
                agent_id,
                e,
                exc_info=True,
            )
            return None

        if not isinstance(payload, dict):
            return None

        raw_reason = payload.get("interrupt_reason", "runtime_injection_available")
        interrupt_reason = str(raw_reason).strip() or "runtime_injection_available"
        injected_content = payload.get("injected_content")
        if injected_content is not None:
            injected_content = str(injected_content)

        return {
            "interrupt_reason": interrupt_reason,
            "injected_content": injected_content,
        }

    async def _execute_background_tool_target(
        self,
        tool_name: str,
        tool_type: str,
        arguments: dict[str, Any],
    ) -> tuple[str, bool]:
        """Execute a target tool for a background job."""
        if tool_type == "custom":
            call = {
                "name": tool_name,
                "arguments": json.dumps(arguments),
            }
            final_result = ""
            async for chunk in self.stream_custom_tool_execution(call):
                if chunk.completed:
                    final_result = chunk.accumulated_result
            final_text = str(final_result or "").strip()
            if not final_text or final_text == "Tool executed successfully":
                return ("No final result payload captured from custom tool execution", True)
            return (final_text, False)

        if tool_type == "mcp":
            result_str, result_obj = await self._execute_mcp_function_with_retry(
                tool_name,
                json.dumps(arguments),
            )
            is_error = bool(result_str.startswith("Error:"))

            display_result = result_str
            if not is_error and result_obj is not None and hasattr(result_obj, "content"):
                extracted = self._extract_text_from_content(result_obj.content)
                if extracted:
                    display_result = extracted
            return (display_result, is_error)

        raise ValueError(f"Unsupported background tool type: {tool_type}")

    async def _run_background_tool_job(self, job_id: str) -> None:
        """Execute a background job and persist its terminal state."""
        job = self._background_tool_jobs.get(job_id)
        if not job:
            return

        job.started_at = time.time()
        try:
            result, is_error = await self._execute_background_tool_target(
                job.tool_name,
                job.tool_type,
                job.arguments,
            )
            if is_error:
                job.status = "error"
                job.error = result
            else:
                job.status = "completed"
                job.result = result
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = job.error or "Background tool execution cancelled"
            raise
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = f"Background tool failed: {e}"
            logger.warning(
                f"[{self.backend_name}] Background tool {job.tool_name} failed: {e}",
                exc_info=True,
            )
        finally:
            job.completed_at = time.time()
            self._background_tool_tasks.pop(job_id, None)
            if job.status in BACKGROUND_TOOL_TERMINAL_STATUSES:
                self._enqueue_completed_background_job(job)

    async def _start_background_tool_job(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        source_call_id: str | None = None,
    ) -> BackgroundToolJob:
        """Start a background job for a custom or MCP tool."""
        tool_type = self._resolve_background_tool_type(tool_name)
        if tool_type is None:
            raise ValueError(
                f"Tool '{tool_name}' is not available for background execution",
            )
        self._validate_background_tool_prerequisites(tool_name)

        job_id = f"bgtool_{uuid.uuid4().hex[:12]}"
        job = BackgroundToolJob(
            job_id=job_id,
            tool_name=tool_name,
            tool_type=tool_type,
            arguments=dict(arguments),
            status="running",
            created_at=time.time(),
            source_call_id=source_call_id,
        )
        self._background_tool_jobs[job_id] = job
        self._background_tool_tasks[job_id] = asyncio.create_task(
            self._run_background_tool_job(job_id),
            name=f"background_tool:{tool_name}:{job_id}",
        )
        return job

    def _trigger_subagent_spawn_callback(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        source_call_id: str | None = None,
    ) -> None:
        """Trigger immediate subagent-card callback for spawn requests."""
        if not self._is_subagent_spawn_target_tool(tool_name):
            return
        callback = getattr(self, "_subagent_spawn_callback", None)
        if callback is None:
            return

        import threading

        safe_call_id = str(source_call_id or f"spawn_subagent_{uuid.uuid4().hex[:8]}")
        try:
            thread = threading.Thread(
                target=callback,
                args=(tool_name, dict(arguments), safe_call_id),
                daemon=True,
            )
            thread.start()
        except Exception as e:  # noqa: BLE001
            logger.debug("Subagent spawn callback failed: %s", e)

    async def _start_background_subagent_spawn(
        self,
        tool_name: str,
        target_arguments: dict[str, Any],
        source_call_id: str | None = None,
    ) -> dict[str, Any]:
        """Treat wrapped subagent spawns like direct spawn_subagents(background=true)."""
        normalized_arguments = self._normalize_subagent_spawn_background_arguments(
            target_arguments,
        )
        self._trigger_subagent_spawn_callback(
            tool_name,
            normalized_arguments,
            source_call_id=source_call_id,
        )

        result_str, result_obj = await self._execute_mcp_function_with_retry(
            tool_name,
            json.dumps(normalized_arguments),
        )
        if result_str.startswith("Error:"):
            return {
                "success": False,
                "error": result_str.removeprefix("Error:").strip() or result_str,
            }

        display_result = result_str
        if result_obj is not None and hasattr(result_obj, "content"):
            extracted = self._extract_text_from_content(result_obj.content)
            if extracted:
                display_result = extracted

        payload = self._parse_json_or_python_dict(display_result)
        if isinstance(payload, dict):
            if payload.get("success") is True and "mode" not in payload:
                payload["mode"] = "background"
            return self._attach_subagent_background_ids(payload)

        return {
            "success": True,
            "operation": "spawn_subagents",
            "mode": "background",
            "result": display_result,
        }

    @staticmethod
    def _attach_subagent_background_ids(payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure subagent background payloads expose both job and subagent IDs."""
        subagents_raw = payload.get("subagents")
        if not isinstance(subagents_raw, list):
            return payload

        subagents: list[dict[str, Any]] = []
        job_ids: list[str] = []
        for item in subagents_raw:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            subagent_id = str(entry.get("subagent_id") or entry.get("id") or "").strip()
            job_id = str(entry.get("job_id") or subagent_id).strip()
            if subagent_id:
                entry["subagent_id"] = subagent_id
            if job_id:
                entry["job_id"] = job_id
                job_ids.append(job_id)
            subagents.append(entry)

        if subagents:
            payload["subagents"] = subagents

        if not job_ids:
            return payload

        unique_job_ids = list(dict.fromkeys(job_ids))
        payload.setdefault("job_ids", unique_job_ids)

        if len(unique_job_ids) == 1:
            payload.setdefault("job_id", unique_job_ids[0])
            first_subagent_id = str(subagents[0].get("subagent_id") or "").strip() if subagents else ""
            if first_subagent_id:
                payload.setdefault("subagent_id", first_subagent_id)

        return payload

    async def _start_background_tool_from_request(
        self,
        arguments: dict[str, Any],
        source_call_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle custom_tool__start_background_tool."""
        tool_name, target_arguments, parse_error = self._extract_background_start_request(arguments)
        if parse_error:
            return {"success": False, "error": parse_error}

        if self._is_subagent_spawn_target_tool(tool_name):
            try:
                return await self._start_background_subagent_spawn(
                    tool_name,
                    target_arguments,
                    source_call_id=source_call_id,
                )
            except Exception as e:  # noqa: BLE001
                return {"success": False, "error": str(e)}

        try:
            job = await self._start_background_tool_job(
                tool_name,
                target_arguments,
                source_call_id=source_call_id,
            )
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": str(e)}

        payload = self._serialize_background_job(job)
        payload.update(
            {
                "success": True,
                "message": f"Started {tool_name} in background",
            },
        )
        return payload

    def _extract_background_start_request(
        self,
        arguments: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        """Extract target tool name/args from flexible start_background_tool payload."""
        tool_name = str(
            arguments.get("tool_name") or arguments.get("tool") or "",
        ).strip()
        if not tool_name:
            return ("", {}, "tool_name is required")

        if "arguments" in arguments and arguments.get("arguments") is not None:
            target_arguments: Any = arguments.get("arguments")
        elif "args" in arguments and arguments.get("args") is not None:
            target_arguments = arguments.get("args")
        else:
            target_arguments = {key: value for key, value in arguments.items() if key not in {"tool_name", "tool", "arguments", "args"}}

        if target_arguments is None:
            target_arguments = {}

        try:
            target_arguments, decode_passes = normalize_json_object_argument(
                target_arguments,
                field_name="arguments",
            )
        except ValueError:
            return ("", {}, "arguments must be a JSON object")
        if decode_passes > 1:
            logger.info(
                "[BackgroundTools] Normalized %s decode passes for start arguments (%s)",
                decode_passes,
                tool_name,
            )

        # Merge top-level extras (if any) without overriding explicit nested args.
        top_level_extras = {key: value for key, value in arguments.items() if key not in {"tool_name", "tool", "arguments", "args"}}
        for key, value in top_level_extras.items():
            target_arguments.setdefault(key, value)

        return (tool_name, target_arguments, None)

    async def _get_background_tool_status_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__get_background_tool_status."""
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return {"success": False, "error": "job_id is required"}

        job = self._background_tool_jobs.get(job_id)
        if job:
            payload = self._serialize_background_job(job)
            payload["success"] = True
            return payload

        # Check delegate for subagent-managed jobs
        delegate = self._background_tool_delegate
        if delegate:
            try:
                if await delegate.owns(job_id):
                    return await delegate.get_status(job_id)
            except Exception:
                logger.debug("[BackgroundTools] Delegate get_status failed for %s", job_id, exc_info=True)

        return {"success": False, "error": f"Background job not found: {job_id}"}

    async def _get_background_tool_result_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__get_background_tool_result."""
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return {"success": False, "error": "job_id is required"}

        job = self._background_tool_jobs.get(job_id)
        if job:
            ready = job.status in BACKGROUND_TOOL_TERMINAL_STATUSES
            payload = self._serialize_background_job(job, include_result=True)
            payload.update({"success": True, "ready": ready})
            self._annotate_custom_tool_outcome_from_payload(payload, ready=ready)
            if not ready:
                payload["message"] = "Background tool still running"
            return payload

        # Check delegate for subagent-managed jobs
        delegate = self._background_tool_delegate
        if delegate:
            try:
                if await delegate.owns(job_id):
                    return await delegate.get_result(job_id)
            except Exception:
                logger.debug("[BackgroundTools] Delegate get_result failed for %s", job_id, exc_info=True)

        return {"success": False, "error": f"Background job not found: {job_id}"}

    @staticmethod
    def _coerce_background_wait_timeout(arguments: dict[str, Any]) -> float:
        """Normalize wait timeout to a safe bounded value."""
        raw_timeout = arguments.get(
            "timeout_seconds",
            BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS,
        )
        try:
            timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = BACKGROUND_TOOL_WAIT_DEFAULT_TIMEOUT_SECONDS
        if timeout_seconds < 0:
            return 0.0
        return min(timeout_seconds, BACKGROUND_TOOL_WAIT_MAX_TIMEOUT_SECONDS)

    def _next_waitable_background_job(self) -> BackgroundToolJob | None:
        """Get the next unseen terminal background job for wait calls."""
        candidates = [job for job in self._background_tool_jobs.values() if job.status in BACKGROUND_TOOL_TERMINAL_STATUSES and job.job_id not in self._background_tool_wait_seen_ids]
        if not candidates:
            return None
        candidates.sort(
            key=lambda job: (
                job.completed_at if job.completed_at is not None else job.created_at,
                job.created_at,
            ),
        )
        return candidates[0]

    async def _wait_for_background_tool_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__wait_for_background_tool."""
        timeout_seconds = self._coerce_background_wait_timeout(arguments)
        wait_started_at = time.time()

        while True:
            payload = self._pop_next_pending_background_tool_result()
            if payload is not None:
                job_id = str(payload.get("job_id", "")).strip()
                if job_id:
                    self._background_tool_wait_seen_ids.add(job_id)
                payload.update(
                    {
                        "success": True,
                        "ready": True,
                        "waited_seconds": round(time.time() - wait_started_at, 3),
                    },
                )
                self._annotate_custom_tool_outcome_from_payload(payload, ready=True)
                return payload

            interrupt_payload = await self._get_background_wait_interrupt_payload()
            if interrupt_payload is not None:
                return {
                    "success": True,
                    "ready": False,
                    "interrupted": True,
                    "interrupt_reason": interrupt_payload.get("interrupt_reason"),
                    "injected_content": interrupt_payload.get("injected_content"),
                    "waited_seconds": round(time.time() - wait_started_at, 3),
                    "message": "Background wait interrupted by runtime input",
                }

            elapsed = time.time() - wait_started_at
            if elapsed >= timeout_seconds:
                return {
                    "success": True,
                    "ready": False,
                    "timed_out": True,
                    "waited_seconds": round(elapsed, 3),
                    "message": "No background tool completed before timeout",
                }

            sleep_seconds = min(
                BACKGROUND_TOOL_WAIT_POLL_INTERVAL_SECONDS,
                max(timeout_seconds - elapsed, 0.0),
            )
            if sleep_seconds <= 0:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(sleep_seconds)

    async def _cancel_background_tool_from_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle custom_tool__cancel_background_tool."""
        job_id = str(arguments.get("job_id", "")).strip()
        if not job_id:
            return {"success": False, "error": "job_id is required"}

        job = self._background_tool_jobs.get(job_id)
        if job:
            task = self._background_tool_tasks.get(job_id)
            if task and not task.done():
                job.status = "cancelled"
                job.error = "Cancelled by user request"
                task.cancel()

            payload = self._serialize_background_job(job)
            payload["success"] = True
            return payload

        # Check delegate for subagent-managed jobs
        delegate = self._background_tool_delegate
        if delegate:
            try:
                if await delegate.owns(job_id):
                    return await delegate.cancel(job_id)
            except Exception:
                logger.debug("[BackgroundTools] Delegate cancel failed for %s", job_id, exc_info=True)

        return {"success": False, "error": f"Background job not found: {job_id}"}

    @staticmethod
    def _coerce_include_all_background_jobs(arguments: dict[str, Any] | None) -> bool:
        """Normalize include_all flag for background list requests."""
        if not isinstance(arguments, dict):
            return False

        raw_include_all = arguments.get("include_all", arguments.get("all"))
        if isinstance(raw_include_all, bool):
            return raw_include_all
        if isinstance(raw_include_all, str):
            return raw_include_all.strip().lower() in {"1", "true", "yes", "on", "all"}
        return False

    async def _list_background_tools_from_request(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Handle custom_tool__list_background_tools."""
        include_all = self._coerce_include_all_background_jobs(arguments)
        jobs = [self._serialize_background_job(job) for job in self._background_tool_jobs.values() if include_all or job.status not in BACKGROUND_TOOL_TERMINAL_STATUSES]

        # Merge delegate jobs (e.g., subagents)
        delegate = self._background_tool_delegate
        if delegate:
            try:
                delegate_jobs = await delegate.list_jobs(include_all=include_all)
                jobs.extend(delegate_jobs)
            except Exception:
                logger.debug("[BackgroundTools] Delegate list_jobs failed", exc_info=True)

        jobs.sort(key=lambda job: job.get("created_at") or "", reverse=True)
        return {
            "success": True,
            "count": len(jobs),
            "include_all": include_all,
            "jobs": jobs,
        }

    async def _execute_background_management_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        source_call_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch internal background-management custom tools."""
        if tool_name == BACKGROUND_TOOL_START_NAME:
            return await self._start_background_tool_from_request(
                arguments,
                source_call_id=source_call_id,
            )
        if tool_name == BACKGROUND_TOOL_STATUS_NAME:
            return await self._get_background_tool_status_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_RESULT_NAME:
            return await self._get_background_tool_result_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_WAIT_NAME:
            return await self._wait_for_background_tool_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_CANCEL_NAME:
            return await self._cancel_background_tool_from_request(arguments)
        if tool_name == BACKGROUND_TOOL_LIST_NAME:
            return await self._list_background_tools_from_request(arguments)

        return {"success": False, "error": f"Unknown background management tool: {tool_name}"}

    async def _cancel_all_background_tool_jobs(self) -> None:
        """Cancel all running background jobs (called during backend cleanup)."""
        running_tasks: list[asyncio.Task[Any]] = []
        for job_id, task in list(self._background_tool_tasks.items()):
            if task.done():
                continue
            job = self._background_tool_jobs.get(job_id)
            if job:
                job.status = "cancelled"
                job.error = "Cancelled during backend cleanup"
            task.cancel()
            running_tasks.append(task)

        if running_tasks:
            await asyncio.gather(*running_tasks, return_exceptions=True)

    def _categorize_tool_calls(
        self,
        captured_calls: list[dict[str, Any]],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """Categorize tool calls into MCP, custom, and provider categories.

        Args:
            captured_calls: List of tool call dictionaries with name and arguments

        Returns:
            Tuple of (mcp_calls, custom_calls, provider_calls)

        Note:
            Provider calls include workflow tools (new_answer, vote) that must NOT
            be executed by backends.
        """
        mcp_calls: list[dict] = []
        custom_calls: list[dict] = []
        provider_calls: list[dict] = []

        for call in captured_calls:
            call_name = call.get("name", "")

            if call_name in self._mcp_functions:
                mcp_calls.append(call)
            elif call_name in self._custom_tool_names:
                custom_calls.append(call)
            else:
                # Provider calls include workflow tools and unknown tools
                provider_calls.append(call)

        return mcp_calls, custom_calls, provider_calls

    @staticmethod
    def _tool_argument_completeness_score(arguments: Any) -> int:
        """Return a rough completeness score for a tool arguments payload."""
        if arguments is None:
            return 0
        if isinstance(arguments, str):
            return len(arguments.strip())
        if isinstance(arguments, (dict, list)):
            try:
                return len(json.dumps(arguments, ensure_ascii=False))
            except (TypeError, ValueError):
                return len(str(arguments))
        return len(str(arguments))

    def _deduplicate_standard_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        source: str,
    ) -> list[dict[str, Any]]:
        """Deduplicate OpenAI-style tool calls by ID while keeping the richest payload."""
        deduplicated: list[dict[str, Any]] = []
        calls_by_id: dict[str, dict[str, Any]] = {}
        duplicate_ids: set[str] = set()

        for tool_call in tool_calls:
            call_id = str(tool_call.get("id", "") or "").strip()
            if not call_id:
                deduplicated.append(tool_call)
                continue

            existing = calls_by_id.get(call_id)
            if existing is None:
                stored_call = deepcopy(tool_call)
                calls_by_id[call_id] = stored_call
                deduplicated.append(stored_call)
                continue

            duplicate_ids.add(call_id)

            if not existing.get("type") and tool_call.get("type"):
                existing["type"] = tool_call["type"]

            existing_function = existing.setdefault("function", {})
            new_function = tool_call.get("function", {})
            if not isinstance(existing_function, dict):
                existing_function = {}
                existing["function"] = existing_function
            if not isinstance(new_function, dict):
                new_function = {}

            if not existing_function.get("name") and new_function.get("name"):
                existing_function["name"] = new_function["name"]

            existing_args = existing_function.get("arguments")
            new_args = new_function.get("arguments")
            if self._tool_argument_completeness_score(new_args) > self._tool_argument_completeness_score(existing_args):
                existing_function["arguments"] = new_args

        if duplicate_ids:
            duplicate_list = ", ".join(sorted(duplicate_ids))
            logger.warning(
                f"[ToolCalls] Deduplicated {len(duplicate_ids)} duplicate tool_call id(s) from {source}: {duplicate_list}",
            )

        return deduplicated

    def _deduplicate_captured_tool_calls(
        self,
        captured_calls: list[dict[str, Any]],
        *,
        source: str,
    ) -> list[dict[str, Any]]:
        """Deduplicate backend-normalized tool calls by call_id."""
        deduplicated: list[dict[str, Any]] = []
        calls_by_id: dict[str, dict[str, Any]] = {}
        duplicate_ids: set[str] = set()

        for call in captured_calls:
            call_id = str(call.get("call_id", "") or "").strip()
            if not call_id:
                deduplicated.append(call)
                continue

            existing = calls_by_id.get(call_id)
            if existing is None:
                stored_call = deepcopy(call)
                calls_by_id[call_id] = stored_call
                deduplicated.append(stored_call)
                continue

            duplicate_ids.add(call_id)

            if not existing.get("name") and call.get("name"):
                existing["name"] = call["name"]

            existing_args = existing.get("arguments")
            new_args = call.get("arguments")
            if self._tool_argument_completeness_score(new_args) > self._tool_argument_completeness_score(existing_args):
                existing["arguments"] = new_args

        if duplicate_ids:
            duplicate_list = ", ".join(sorted(duplicate_ids))
            logger.warning(
                f"[ToolCalls] Deduplicated {len(duplicate_ids)} duplicate captured tool_call id(s) from {source}: {duplicate_list}",
            )

        return deduplicated

    @abstractmethod
    def _append_tool_result_message(
        self,
        updated_messages: list[dict[str, Any]],
        call: dict[str, Any],
        result: Any,
        tool_type: str,
    ) -> None:
        """Append tool result to messages in backend-specific format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            result: Tool execution result
            tool_type: "custom" or "mcp"

        Each backend must implement this to use its specific message format:
        - ChatCompletions: {"role": "tool", "tool_call_id": ..., "content": ...}
        - Response API: {"type": "function_call_output", "call_id": ..., "output": ...}
        - Claude: {"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "content": ...}]}
        """

    @abstractmethod
    def _append_tool_error_message(
        self,
        updated_messages: list[dict[str, Any]],
        call: dict[str, Any],
        error_msg: str,
        tool_type: str,
    ) -> None:
        """Append tool error to messages in backend-specific format.

        Args:
            updated_messages: Message list to append to
            call: Tool call dictionary with call_id, name, arguments
            error_msg: Error message string
            tool_type: "custom" or "mcp"

        Each backend must implement this using the same format as _append_tool_result_message
        but with error content.
        """

    def _truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens using binary search.

        Args:
            text: Text to truncate
            max_tokens: Target maximum tokens

        Returns:
            Truncated text that fits within token limit
        """
        # Quick check - if already under limit, return as-is
        if self.token_calculator.estimate_tokens(text) <= max_tokens:
            return text

        # Binary search for the right character cutoff
        low, high = 0, len(text)
        result = ""

        while low < high:
            mid = (low + high + 1) // 2
            candidate = text[:mid]
            tokens = self.token_calculator.estimate_tokens(candidate)

            if tokens <= max_tokens:
                result = candidate
                low = mid
            else:
                high = mid - 1

        return result

    def _maybe_evict_large_tool_result(
        self,
        result_text: str,
        tool_name: str,
        call_id: str,
    ) -> EvictionResult:
        """Evict large tool result to file if it exceeds token threshold.

        When tool results exceed TOOL_RESULT_EVICTION_THRESHOLD_TOKENS, they are
        saved to a file in the agent's workspace and replaced with a reference
        message containing a preview. This prevents context window saturation.

        Args:
            result_text: The full tool result text
            tool_name: Name of the tool that produced the result
            call_id: Unique call ID for this tool invocation

        Returns:
            EvictionResult with:
            - text: reference_message if evicted, original_result_text otherwise
            - was_evicted: True if evicted to file, False if kept in memory
        """
        # Estimate token count using tiktoken
        token_count = self.token_calculator.estimate_tokens(result_text)

        if token_count <= TOOL_RESULT_EVICTION_THRESHOLD_TOKENS:
            return EvictionResult(text=result_text, was_evicted=False)

        # Need to evict - get workspace path
        if not self.filesystem_manager or not self.filesystem_manager.cwd:
            logger.error(
                f"[ToolEviction] Cannot evict {tool_name} result "
                f"({token_count:,} tokens, limit {TOOL_RESULT_EVICTION_THRESHOLD_TOKENS:,}) - "
                "no workspace available. Large result kept in context may cause overflow.",
            )
            return EvictionResult(text=result_text, was_evicted=False)

        try:
            # Create eviction directory
            workspace = Path(self.filesystem_manager.cwd)
            eviction_dir = workspace / EVICTED_RESULTS_DIR
            eviction_dir.mkdir(exist_ok=True)

            # Generate filename: tool_name_timestamp_callid.txt
            safe_tool_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in tool_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            short_id = call_id[:8] if call_id else "unknown"
            filename = f"{safe_tool_name}_{timestamp}_{short_id}.txt"
            filepath = eviction_dir / filename

            # Write result to file
            filepath.write_text(result_text, encoding="utf-8")

            # Build token-based preview (~2000 tokens)
            preview = self._truncate_to_token_limit(
                result_text,
                TOOL_RESULT_EVICTION_PREVIEW_TOKENS,
            )
            preview_end_char = len(preview)
            total_chars = len(result_text)

            # Build reference message with character positions for chunked reading
            # Use relative path from workspace for cleaner display
            relative_path = f"{EVICTED_RESULTS_DIR}/{filename}"
            reference = (
                f"[Tool Result Evicted - Too Large for Context]\n\n"
                f"The result from {tool_name} was {token_count:,} tokens / {total_chars:,} chars "
                f"(limit: {TOOL_RESULT_EVICTION_THRESHOLD_TOKENS:,} tokens).\n"
                f"Full result saved to: {relative_path}\n\n"
                f"To read more: start at char {preview_end_char:,}, read in chunks.\n\n"
                f"Preview (chars 0-{preview_end_char:,} of {total_chars:,}):\n{preview}"
            )

            logger.info(
                f"[ToolEviction] Evicted {tool_name} result: " f"{token_count:,} tokens -> {filepath}",
            )

            return EvictionResult(text=reference, was_evicted=True)

        except (OSError, PermissionError, UnicodeEncodeError) as e:
            logger.warning(
                f"[ToolEviction] Failed to evict {tool_name} result ({token_count:,} tokens): {e}. " "Keeping result in memory - this may cause context overflow on next API call.",
                exc_info=True,
            )
            return EvictionResult(text=result_text, was_evicted=False)

    async def _execute_tool_with_logging(
        self,
        call: dict[str, Any],
        config: ToolExecutionConfig,
        updated_messages: list[dict[str, Any]],
        processed_call_ids: set[str],
    ) -> AsyncGenerator[StreamChunk]:
        """Execute a tool with unified logging and error handling.

        Args:
            call: Tool call dictionary with call_id, name, arguments
            config: ToolExecutionConfig specifying execution parameters
            updated_messages: Message list to append results to
            processed_call_ids: Set to track processed call IDs

        Yields:
            StreamChunk objects for status updates, arguments, results, and errors

        Note:
            This method provides defense-in-depth validation to prevent workflow tools
            from being executed. Workflow tools should be filtered by categorization
            logic before reaching this method.
        """
        tool_name = call.get("name", "")
        call_id = call.get("call_id") or str(uuid.uuid4())
        call["call_id"] = call_id  # Ensure call_id is always set for downstream usage
        arguments_str = call.get("arguments", "{}")

        # Create metrics tracker at start
        metric = ToolExecutionMetric(
            tool_name=tool_name,
            tool_type=config.tool_type,
            call_id=call_id,
            agent_id=self.agent_id or "unknown",
            round_number=self._current_round_number,
            start_time=time.time(),
            input_chars=len(arguments_str),
        )

        if tool_name in ["new_answer", "vote", "stop"]:
            error_msg = f"CRITICAL: Workflow tool {tool_name} incorrectly routed to execution"
            logger.error(error_msg)
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_error,
                content=f"{config.error_emoji} {error_msg}",
                source=f"{config.source_prefix}{tool_name}",
            )
            return

        try:
            # Execute PreToolUse hooks if hook manager is available
            if self._general_hook_manager:
                workspace_path = None
                if self.filesystem_manager and getattr(self.filesystem_manager, "cwd", None):
                    workspace_path = str(self.filesystem_manager.cwd)
                hook_context = {
                    "hook_type": "PreToolUse",
                    "session_id": getattr(self, "session_id", ""),
                    "orchestrator_id": getattr(self, "orchestrator_id", ""),
                    "agent_id": self.agent_id,
                    "workspace_path": workspace_path,
                }
                pre_result = await self._general_hook_manager.execute_hooks(
                    HookType.PRE_TOOL_USE,
                    tool_name,
                    arguments_str,
                    hook_context,
                )

                # Emit hook execution events for display (pre-hooks)
                for hook_exec in pre_result.executed_hooks:
                    yield StreamChunk(
                        type="hook_execution",
                        source=self.agent_id,
                        hook_info=hook_exec,
                        tool_call_id=call_id,
                    )

                # Handle deny decision
                if not pre_result.allowed or pre_result.decision == "deny":
                    error_msg = f"Hook denied tool execution: {pre_result.reason or 'No reason provided'}"
                    logger.warning(f"[PreToolUse] {error_msg}")
                    yield StreamChunk(
                        type=config.chunk_type,
                        status=config.status_error,
                        content=f"{config.error_emoji} {error_msg}",
                        source=f"{config.source_prefix}{tool_name}",
                        tool_call_id=call_id,
                    )
                    # Still need to add error result to messages
                    self._append_tool_error_message(
                        updated_messages,
                        call,
                        error_msg,
                        config.tool_type,
                    )
                    processed_call_ids.add(call_id)

                    # Record metric for denied execution
                    metric.end_time = time.time()
                    metric.success = False
                    metric.error_message = error_msg[:500]
                    self._tool_execution_metrics.append(metric)
                    return

                # Use modified arguments if provided
                if pre_result.modified_args is not None:
                    arguments_str = pre_result.modified_args
                    # Update the call dict too for downstream processing
                    call["arguments"] = arguments_str
                    # Update metrics to reflect actual input that will run
                    metric.input_chars = len(arguments_str)

            # Emit structured tool_start event for TUI event pipeline

            emitter = get_event_emitter()
            if emitter:
                try:
                    args_dict = json.loads(arguments_str) if arguments_str else {}
                except (json.JSONDecodeError, TypeError):
                    args_dict = {"raw": arguments_str}
                emitter.emit_tool_start(
                    tool_id=call_id,
                    tool_name=tool_name,
                    args=args_dict,
                    server_name=config.source_prefix.rstrip("_: ") if config.tool_type == "mcp" else None,
                    agent_id=self.agent_id,
                )

            # Yield tool called status
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_called,
                content=f"{config.emoji_prefix} Calling {tool_name}...",
                source=f"{config.source_prefix}{tool_name}",
                tool_call_id=call_id,
            )

            # Yield arguments chunk (arguments_str already extracted above)
            yield StreamChunk(
                type=config.chunk_type,
                status="function_call",
                content=f"Arguments for Calling {tool_name}: {arguments_str}",
                source=f"{config.source_prefix}{tool_name}",
                tool_call_id=call_id,
                display=False,  # Verbose diagnostic - shown in tool card instead
            )

            # Auto-background mode: if a tool call includes background=true or mode=background,
            # schedule it and return a pollable job ID instead of blocking inline execution.
            try:
                parsed_arguments = self._parse_tool_arguments(arguments_str)
            except Exception:
                parsed_arguments = {}

            auto_background = self._should_auto_background_execution(
                tool_name,
                parsed_arguments,
            )
            if auto_background:
                background_args = self._strip_background_control_args(
                    parsed_arguments,
                    tool_name=tool_name,
                )
                try:
                    background_job = await self._start_background_tool_job(
                        tool_name=tool_name,
                        arguments=background_args,
                        source_call_id=call_id,
                    )
                except Exception as e:  # noqa: BLE001
                    error_msg = f"Error starting background execution for {tool_name}: {e}"
                    self._append_tool_error_message(
                        updated_messages,
                        call,
                        error_msg,
                        config.tool_type,
                    )
                    processed_call_ids.add(call_id)
                    yield StreamChunk(
                        type=config.chunk_type,
                        status=config.status_error,
                        content=f"{config.error_emoji} {error_msg}",
                        source=f"{config.source_prefix}{tool_name}",
                        tool_call_id=call_id,
                    )
                    if emitter:
                        emitter.emit_tool_complete(
                            tool_id=call_id,
                            tool_name=tool_name,
                            result=error_msg,
                            elapsed_seconds=time.time() - metric.start_time,
                            status="error",
                            is_error=True,
                            agent_id=self.agent_id,
                        )
                    metric.end_time = time.time()
                    metric.success = False
                    metric.error_message = error_msg[:500]
                    self._tool_execution_metrics.append(metric)
                    return

                background_payload = {
                    "success": True,
                    "status": "background",
                    "job_id": background_job.job_id,
                    "tool_name": tool_name,
                    "message": f"{tool_name} is running in background",
                }
                background_result = json.dumps(background_payload, ensure_ascii=False)

                self._append_tool_result_message(
                    updated_messages,
                    call,
                    background_result,
                    config.tool_type,
                )
                processed_call_ids.add(call_id)

                yield StreamChunk(
                    type=config.chunk_type,
                    status="function_call_output",
                    content=f"Results for Calling {tool_name}: {background_result}",
                    source=f"{config.source_prefix}{tool_name}",
                    tool_call_id=call_id,
                    display=False,
                )
                yield StreamChunk(
                    type=config.chunk_type,
                    status=config.status_response,
                    content=f"🕒 {tool_name} running in background (job_id={background_job.job_id})",
                    source=f"{config.source_prefix}{tool_name}",
                    tool_call_id=call_id,
                )

                if emitter:
                    emitter.emit_tool_complete(
                        tool_id=call_id,
                        tool_name=tool_name,
                        result=background_result,
                        elapsed_seconds=time.time() - metric.start_time,
                        status="background",
                        is_error=False,
                        async_id=background_job.job_id,
                        agent_id=self.agent_id,
                    )

                metric.end_time = time.time()
                metric.output_chars = len(background_result)
                metric.success = True
                self._tool_execution_metrics.append(metric)
                return

            # Media tools default to background mode, so explicit foreground
            # overrides may include control args (for example background=false).
            # Strip these before direct execution to avoid passing them through.
            if self._is_default_media_background_tool(tool_name) and isinstance(parsed_arguments, dict):
                foreground_args = self._strip_background_control_args(
                    parsed_arguments,
                    tool_name=tool_name,
                )
                if foreground_args != parsed_arguments:
                    arguments_str = json.dumps(foreground_args, ensure_ascii=False)
                    call["arguments"] = arguments_str
                    metric.input_chars = len(arguments_str)

            # Special handling for subagent spawn - notify TUI immediately.
            if self._is_subagent_spawn_target_tool(tool_name):
                try:
                    args_for_callback = self._parse_tool_arguments(arguments_str) if arguments_str else {}
                except Exception:
                    args_for_callback = {}
                self._trigger_subagent_spawn_callback(
                    tool_name,
                    args_for_callback,
                    source_call_id=call_id,
                )

            # Record tool call to execution trace (if available via mixin)
            if hasattr(self, "_execution_trace") and self._execution_trace:
                try:
                    args_dict = json.loads(arguments_str) if arguments_str else {}
                except (json.JSONDecodeError, TypeError):
                    args_dict = {"raw": arguments_str}
                self._execution_trace.add_tool_call(name=tool_name, args=args_dict)

            # Execute tool via callback with observability span
            result = None
            result_str = ""
            result_obj = None

            # Create span for hierarchical tracing (similar to MCP tools)
            tracer = get_tracer()
            span_attributes = {
                "tool.name": tool_name,
                "tool.type": config.tool_type,
            }
            if self.agent_id:
                span_attributes["massgen.agent_id"] = self.agent_id
            if self._current_round_number is not None:
                span_attributes["massgen.round"] = self._current_round_number
            if self._current_round_type:
                span_attributes["massgen.round_type"] = self._current_round_type

            # Determine span name based on tool type
            span_name = f"custom_tool.{tool_name}" if config.tool_type == "custom" else f"mcp_tool.{tool_name}"

            with tracer.span(span_name, attributes=span_attributes) as tool_span:
                if config.tool_type == "custom":
                    # Check if execution_callback returns an async generator (streaming)
                    callback_result = config.execution_callback(call)

                    # Handle async generator (streaming custom tools)
                    if hasattr(callback_result, "__aiter__"):
                        # This is an async generator - stream intermediate results
                        result_meta_info = None
                        async for chunk in callback_result:
                            # Yield intermediate chunks if available
                            if hasattr(chunk, "data") and chunk.data and not chunk.completed:
                                # Stream intermediate output to user
                                yield StreamChunk(
                                    type=config.chunk_type,
                                    status="custom_tool_output",
                                    content=chunk.data,
                                    source=f"{config.source_prefix}{tool_name}",
                                    tool_call_id=call_id,
                                )
                            elif hasattr(chunk, "completed") and chunk.completed:
                                # Extract final accumulated result and metadata
                                result_str = chunk.accumulated_result
                                result_meta_info = getattr(chunk, "meta_info", None)
                        # Wrap result with meta_info if multimodal data is present
                        if result_meta_info:
                            result = types.SimpleNamespace(
                                text=result_str,
                                meta_info=result_meta_info,
                            )
                        else:
                            result = result_str
                    else:
                        # Handle regular await (non-streaming custom tools)
                        result = await callback_result
                        result_str = str(result)
                else:  # MCP
                    result_str, result_obj = await config.execution_callback(
                        call["name"],
                        call["arguments"],
                    )
                    # Preserve CallToolResult object for proper text extraction in _append_tool_result_message
                    result = result_obj if result_obj is not None else result_str

                # Capture execution end time inside span
                execution_end_time = time.time()
                tool_span.set_attribute("tool.execution_time_ms", (execution_end_time - metric.start_time) * 1000)

            # Note: execution_end_time is now set inside the span

            # Check for MCP failure after retries
            if config.tool_type == "mcp" and result_str.startswith("Error:"):
                logger.warning(
                    f"MCP tool {tool_name} failed after retries: {result_str}",
                )
                error_msg = result_str
                self._append_tool_error_message(
                    updated_messages,
                    call,
                    error_msg,
                    config.tool_type,
                )
                processed_call_ids.add(call.get("call_id", ""))
                yield StreamChunk(
                    type=config.chunk_type,
                    status=config.status_error,
                    content=f"{config.error_emoji} {error_msg}",
                    source=f"{config.source_prefix}{tool_name}",
                    tool_call_id=call_id,
                )
                # Emit structured tool_complete event for MCP failure
                if emitter:
                    emitter.emit_tool_complete(
                        tool_id=call_id,
                        tool_name=tool_name,
                        result=error_msg,
                        elapsed_seconds=execution_end_time - metric.start_time,
                        status="error",
                        is_error=True,
                        agent_id=self.agent_id,
                    )

                # Record MCP failure metrics (use pre-captured execution end time)
                metric.end_time = execution_end_time
                metric.success = False
                metric.error_message = error_msg[:500]
                self._tool_execution_metrics.append(metric)

                # Log structured tool execution for observability (MCP failure case)
                execution_time_ms = (metric.end_time - metric.start_time) * 1000
                log_tool_execution(
                    agent_id=self.agent_id or "unknown",
                    tool_name=tool_name,
                    tool_type=config.tool_type,
                    execution_time_ms=execution_time_ms,
                    success=False,
                    input_chars=len(arguments_str),
                    output_chars=0,
                    error_message=error_msg[:500],
                    arguments_preview=arguments_str[:200] if arguments_str else None,
                    round_number=self._current_round_number,
                    round_type=self._current_round_type,
                )
                return

            # Extract result text for eviction check - handle MCP CallToolResult properly
            if hasattr(result, "content") and not isinstance(result, (dict, str)):
                # MCP CallToolResult - extract text from content list
                extracted = self._extract_text_from_content(result.content)
                result_text_for_eviction = extracted if extracted is not None else str(result)
            else:
                result_text_for_eviction = getattr(result, "text", None) or str(result)

            # Check for large result eviction before appending
            eviction = self._maybe_evict_large_tool_result(
                result_text_for_eviction,
                tool_name,
                call_id,
            )

            # Execute PostToolUse hooks if hook manager is available
            post_hook_injection = None
            post_hook_reminder = None
            if self._general_hook_manager:
                workspace_path = None
                if self.filesystem_manager and getattr(self.filesystem_manager, "cwd", None):
                    workspace_path = str(self.filesystem_manager.cwd)
                hook_context = {
                    "hook_type": "PostToolUse",
                    "session_id": getattr(self, "session_id", ""),
                    "orchestrator_id": getattr(self, "orchestrator_id", ""),
                    "agent_id": self.agent_id,
                    "workspace_path": workspace_path,
                }
                post_result = await self._general_hook_manager.execute_hooks(
                    HookType.POST_TOOL_USE,
                    tool_name,
                    arguments_str,
                    hook_context,
                    tool_output=result_text_for_eviction,
                )

                # Emit hook execution events for display (post-hooks)
                logger.info(
                    f"[PostToolUse] Hook results - executed_hooks count: {len(post_result.executed_hooks)}, " f"has_inject: {post_result.inject is not None}",
                )
                for hook_exec in post_result.executed_hooks:
                    logger.info(f"[PostToolUse] Emitting hook_execution chunk for {hook_exec.get('hook_name', 'unknown')}")
                    yield StreamChunk(
                        type="hook_execution",
                        source=self.agent_id,
                        hook_info=hook_exec,
                        tool_call_id=call_id,
                    )

                # Handle injection content from PostToolUse hooks
                if post_result.inject:
                    inject_data = post_result.inject
                    inject_content = inject_data.get("content", "")
                    inject_strategy = inject_data.get("strategy", "tool_result")

                    if inject_strategy == "user_message":
                        # Will be injected as a user message after tool result
                        post_hook_reminder = inject_content
                    else:
                        # Default: append to tool result
                        post_hook_injection = inject_content

                    logger.info(
                        f"[PostToolUse] Hook injection for {tool_name}: strategy={inject_strategy}, content_len={len(inject_content)}",
                    )
                    # Log injection content at debug level (may contain sensitive data)
                    if inject_content:
                        preview = inject_content[:500] + ("..." if len(inject_content) > 500 else "")
                        logger.debug(f"[PostToolUse] Injection preview:\n{preview}")

            # Use hook injection as the injection content
            # Mid-stream injection is now handled via MidStreamInjectionHook in the hook framework
            injection_content = post_hook_injection

            # Append result to messages (potentially evicted, potentially with injection)
            if eviction.was_evicted:
                # Create a new result with the evicted reference
                result_text = eviction.text
                if injection_content:
                    result_text = f"{result_text}\n{injection_content}"

                if hasattr(result, "text"):
                    evicted_result = types.SimpleNamespace(
                        text=result_text,
                        meta_info=getattr(result, "meta_info", None),
                    )
                    self._append_tool_result_message(
                        updated_messages,
                        call,
                        evicted_result,
                        config.tool_type,
                    )
                else:
                    self._append_tool_result_message(
                        updated_messages,
                        call,
                        result_text,
                        config.tool_type,
                    )
            else:
                # Non-evicted result - potentially add injection
                if injection_content:
                    if hasattr(result, "text"):
                        modified_result = types.SimpleNamespace(
                            text=f"{result.text}\n{injection_content}",
                            meta_info=getattr(result, "meta_info", None),
                        )
                        self._append_tool_result_message(
                            updated_messages,
                            call,
                            modified_result,
                            config.tool_type,
                        )
                    else:
                        modified_result = f"{str(result)}\n{injection_content}"
                        self._append_tool_result_message(
                            updated_messages,
                            call,
                            modified_result,
                            config.tool_type,
                        )
                else:
                    self._append_tool_result_message(
                        updated_messages,
                        call,
                        result,
                        config.tool_type,
                    )

            # Inject hook-based reminder as user message (from PostToolUse hooks)
            # Reminder extraction is now handled by HighPriorityTaskReminderHook which formats the content
            if post_hook_reminder:
                hook_reminder_message = {
                    "role": "user",
                    "content": post_hook_reminder,  # Already formatted by HighPriorityTaskReminderHook
                }
                updated_messages.append(hook_reminder_message)
                # Log first 100 chars, stripping formatting for readability
                log_content = post_hook_reminder.replace("=", "").strip()[:100]
                logger.info(f"[PostToolUse Hook] Injected reminder for {tool_name}: {log_content}...")

            # Yield results chunk
            # For MCP tools, try to extract text from result_obj if available
            display_result = result_str
            if config.tool_type == "mcp" and result_obj:
                try:
                    if hasattr(result_obj, "content") and isinstance(
                        result_obj.content,
                        list,
                    ):
                        if len(result_obj.content) > 0 and hasattr(
                            result_obj.content[0],
                            "text",
                        ):
                            display_result = result_obj.content[0].text
                except (AttributeError, IndexError, TypeError):
                    pass  # Fall back to result_str

            # If result was evicted, show the reference message in streaming output
            if eviction.was_evicted:
                display_result = eviction.text

            yield StreamChunk(
                type=config.chunk_type,
                status="function_call_output",
                content=f"Results for Calling {tool_name}: {display_result}",
                source=f"{config.source_prefix}{tool_name}",
                tool_call_id=call_id,
                display=False,  # Verbose diagnostic - shown in tool card instead
            )

            # Yield injection chunk if there was mid-stream injection
            if injection_content:
                # Truncate for display but show it happened
                display_injection = injection_content[:300] + "..." if len(injection_content) > 300 else injection_content
                yield StreamChunk(
                    type=config.chunk_type,
                    status="injection",
                    content=f"📥 [INJECTION] {display_injection}",
                    source="mid_stream_injection",
                    tool_call_id=call_id,
                )

            # Yield reminder chunk if there was a user_message hook injection
            if post_hook_reminder:
                # Extract first line for display (skip separator lines)
                reminder_lines = [line for line in post_hook_reminder.split("\n") if line.strip() and "===" not in line]
                display_reminder = reminder_lines[0] if reminder_lines else "System reminder"
                yield StreamChunk(
                    type=config.chunk_type,
                    status="reminder",
                    content=f"💡 [REMINDER] {display_reminder}",
                    source="high_priority_task_reminder",
                    tool_call_id=call_id,
                )

            # Yield completion status
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_response,
                content=f"{config.success_emoji} {tool_name} completed",
                source=f"{config.source_prefix}{tool_name}",
                tool_call_id=call_id,
            )

            # Emit structured tool_complete event for TUI event pipeline
            if emitter:
                emitter.emit_tool_complete(
                    tool_id=call_id,
                    tool_name=tool_name,
                    result=display_result,
                    elapsed_seconds=execution_end_time - metric.start_time,
                    status="success",
                    is_error=False,
                    agent_id=self.agent_id,
                )

            processed_call_ids.add(call.get("call_id", ""))
            logger.info(f"Executed {config.tool_type} tool: {tool_name}")

            # Debug delay: Apply after N tool calls to allow other agents to inject
            # Note: Set flag before sleep to prevent parallel tools from also triggering delay
            if self._debug_delay_seconds > 0 and not self._debug_delay_applied:
                self._debug_tool_call_count += 1
                if self._debug_tool_call_count >= self._debug_delay_after_n_tools:
                    self._debug_delay_applied = True  # Set immediately to prevent race conditions
                    logger.info(
                        f"[{self.backend_name}] Applying debug delay of {self._debug_delay_seconds}s after {self._debug_tool_call_count} tool calls for agent {self.agent_id}",
                    )
                    await asyncio.sleep(self._debug_delay_seconds)

            # Record successful execution metrics (use pre-captured time, not current time
            # which would include time spent waiting for stream consumers)
            metric.end_time = execution_end_time
            metric.output_chars = len(display_result)
            metric.success = True
            self._tool_execution_metrics.append(metric)

            # Log structured tool execution for observability
            execution_time_ms = (metric.end_time - metric.start_time) * 1000
            log_tool_execution(
                agent_id=self.agent_id or "unknown",
                tool_name=tool_name,
                tool_type=config.tool_type,
                execution_time_ms=execution_time_ms,
                success=True,
                input_chars=len(arguments_str),
                output_chars=len(display_result),
                arguments_preview=arguments_str[:200] if arguments_str else None,
                output_preview=display_result[:200] if display_result else None,
                round_number=self._current_round_number,
                round_type=self._current_round_type,
            )

        except Exception as e:
            # Log error
            logger.error(f"Error executing {config.tool_type} tool {tool_name}: {e}")

            # Build error message
            error_msg = f"Error executing {tool_name}: {str(e)}"

            # Yield arguments chunk for context
            arguments_str = call.get("arguments", "{}")
            yield StreamChunk(
                type=config.chunk_type,
                status="function_call",
                content=f"Arguments for Calling {tool_name}: {arguments_str}",
                source=f"{config.source_prefix}{tool_name}",
                tool_call_id=call_id,
                display=False,  # Verbose diagnostic - shown in tool card instead
            )

            # Yield error status chunk
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_error,
                content=f"{config.error_emoji} {error_msg}",
                source=f"{config.source_prefix}{tool_name}",
                tool_call_id=call_id,
            )

            # Emit structured tool_complete event for exception
            if emitter:
                emitter.emit_tool_complete(
                    tool_id=call_id,
                    tool_name=tool_name,
                    result=error_msg,
                    elapsed_seconds=time.time() - metric.start_time,
                    status="error",
                    is_error=True,
                    agent_id=self.agent_id,
                )

            # Append error to messages
            self._append_tool_error_message(
                updated_messages,
                call,
                error_msg,
                config.tool_type,
            )

            processed_call_ids.add(call.get("call_id", ""))

            # Record failed execution metrics
            metric.end_time = time.time()
            metric.success = False
            metric.error_message = str(e)[:500]  # Truncate long errors
            self._tool_execution_metrics.append(metric)

            # Log structured tool execution for observability (failure case)
            execution_time_ms = (metric.end_time - metric.start_time) * 1000
            log_tool_execution(
                agent_id=self.agent_id or "unknown",
                tool_name=tool_name,
                tool_type=config.tool_type,
                execution_time_ms=execution_time_ms,
                success=False,
                input_chars=len(arguments_str),
                output_chars=0,
                error_message=str(e)[:500],
                arguments_preview=arguments_str[:200] if arguments_str else None,
                round_number=self._current_round_number,
                round_type=self._current_round_type,
            )

    async def _run_tool_call(
        self,
        call: dict[str, Any],
        config: ToolExecutionConfig,
        semaphore: asyncio.Semaphore | None = None,
    ) -> ToolExecutionResult:
        """Run a single tool call and collect its chunks/messages.

        This wraps _execute_tool_with_logging so parallel execution can keep
        per-call side effects isolated until we're ready to merge them into
        shared message history.
        """
        per_call_messages: list[dict[str, Any]] = []
        per_call_processed_ids: set[str] = set()
        chunks: list[StreamChunk] = []
        exc: BaseException | None = None

        async def _inner() -> None:
            nonlocal exc
            try:
                async for chunk in self._execute_tool_with_logging(
                    call,
                    config,
                    per_call_messages,
                    per_call_processed_ids,
                ):
                    chunks.append(chunk)
            except Exception as e:  # noqa: BLE001
                # Most execution errors are handled inside _execute_tool_with_logging.
                # This is a safety net for unexpected failures.
                tool_name = call.get("name", "")
                logger.error(
                    f"Unexpected error while executing tool {tool_name}: {e}",
                    exc_info=True,
                )
                exc = e

        if semaphore:
            async with semaphore:
                await _inner()
        else:
            await _inner()

        return ToolExecutionResult(
            call=call,
            chunks=chunks,
            messages=per_call_messages,
            exception=exc,
        )

    async def _execute_tool_calls(
        self,
        all_calls: list[dict[str, Any]],
        tool_config_for_call: Callable[[dict[str, Any]], ToolExecutionConfig],
        all_params: dict[str, Any],
        updated_messages: list[dict[str, Any]],
        processed_call_ids: set[str],
        log_prefix: str,
        chunk_adapter: Callable[[StreamChunk], Any],
    ) -> AsyncGenerator[Any]:
        """Execute a batch of tool calls with optional parallelism.

        This centralizes the parallel/sequential scheduling logic so all
        backends share the same behavior and formatting for tool execution.
        """
        if not all_calls:
            return

        # Default to parallel execution for performance (can be disabled via config)
        concurrent_execution = all_params.get("concurrent_tool_execution", True)

        # SEQUENTIAL EXECUTION
        if not concurrent_execution or len(all_calls) <= 1:
            reason = "disabled by config" if concurrent_execution is False else "single tool"
            logger.info(f"{log_prefix} Executing {len(all_calls)} tools sequentially ({reason})")

            for call in all_calls:
                config = tool_config_for_call(call)
                async for chunk in self._execute_tool_with_logging(
                    call,
                    config,
                    updated_messages,
                    processed_call_ids,
                ):
                    yield chunk_adapter(chunk)
            return

        # PARALLEL EXECUTION WITH CONCURRENCY CONTROL
        max_concurrent = all_params.get("max_concurrent_tools", 10)
        semaphore = asyncio.Semaphore(max_concurrent) if max_concurrent else None
        logger.info(
            f"{log_prefix} Executing {len(all_calls)} tools in parallel (max concurrent: {max_concurrent or 'unlimited'})",
        )

        # Wrap each call so we know its index when it completes.
        async def _runner(
            idx: int,
            call: dict[str, Any],
            config: ToolExecutionConfig,
        ) -> tuple[int, ToolExecutionResult]:
            result = await self._run_tool_call(call, config, semaphore)
            return idx, result

        tasks: list[asyncio.Task[tuple[int, ToolExecutionResult]]] = []
        for idx, call in enumerate(all_calls):
            config = tool_config_for_call(call)
            task = asyncio.create_task(_runner(idx, call, config))
            tasks.append(task)

        results_by_index: dict[int, ToolExecutionResult] = {}

        # Stream each tool's output as soon as it finishes, then clear its chunk buffer.
        for fut in asyncio.as_completed(tasks):
            try:
                idx, result = await fut
            except Exception as e:  # noqa: BLE001
                # Extremely defensive: _run_tool_call already catches most errors.
                error_msg = f"Tool execution task failed: {e}"
                logger.error(
                    f"{log_prefix} {error_msg}",
                    exc_info=True,
                )
                continue

            results_by_index[idx] = result

            # If _execute_tool_with_logging surfaced an unexpected exception, emit a summary chunk.
            if result.exception is not None:
                call = result.call
                tool_name = call.get("name", "")
                config = tool_config_for_call(call)
                error_msg = f"Tool execution failed: {result.exception}"
                logger.error(
                    f"{log_prefix} {error_msg}",
                    exc_info=True,
                )
                error_chunk = StreamChunk(
                    type=config.chunk_type,
                    status=config.status_error,
                    content=f"{config.error_emoji} {error_msg}",
                    source=f"{config.source_prefix}{tool_name}",
                )
                yield chunk_adapter(error_chunk)

                # Ensure error is reflected in conversation history as well.
                self._append_tool_error_message(
                    updated_messages,
                    call,
                    error_msg,
                    config.tool_type,
                )
                call_id = call.get("call_id", "")
                if call_id:
                    processed_call_ids.add(call_id)
            else:
                # Normal case: stream all collected chunks for this tool, then clear.
                for chunk in result.chunks:
                    yield chunk_adapter(chunk)
                result.chunks.clear()

        # After all tools complete, merge buffered messages into history in API order.
        all_per_call_messages: list[list[dict[str, Any]]] = []
        for idx, call in enumerate(all_calls):
            result = results_by_index.get(idx)
            if not result:
                continue

            if result.messages:
                all_per_call_messages.append(result.messages)

            call_id = call.get("call_id", "")
            if call_id:
                processed_call_ids.add(call_id)

        self._merge_parallel_tool_results(updated_messages, all_per_call_messages)

    def _merge_parallel_tool_results(
        self,
        updated_messages: list[dict[str, Any]],
        all_per_call_messages: list[list[dict[str, Any]]],
    ) -> None:
        """Merge per-call tool result messages into shared history after parallel execution.

        Default implementation: append each per-call message list directly (correct for
        OpenAI/Gemini, where each tool result is its own message).

        Override in backends that require all tool results for a turn to be in a single
        message (e.g. Claude, where the API enforces tool_result consolidation).
        """
        for msgs in all_per_call_messages:
            updated_messages.extend(msgs)

    def filter_enforcement_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        unknown_tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return the subset of tool_calls that are safe to send tool_result enforcement for.

        Default: return all calls unchanged.  For OpenAI/Gemini the assistant message
        always preserves the tool_calls field, so every tool_result is valid.

        Override in backends where unknown tool calls are stripped from assistant message
        history, making tool_result enforcement produce an API error (e.g. Claude).
        """
        return tool_calls

    async def _stream_tool_execution_via_nlip(
        self,
        call: dict[str, Any],
        config: ToolExecutionConfig,
        updated_messages: list[dict[str, Any]],
        processed_call_ids: set[str],
    ) -> AsyncGenerator[StreamChunk]:
        """Stream NLIP tool execution while mirroring native telemetry."""
        if not self._nlip_router:
            raise RuntimeError("NLIP router is not configured")

        tool_name = call.get("name", "")
        call_id = call.get("call_id", "")
        arguments_str = call.get("arguments", "{}")

        # Emit the same status + argument chunks as the native path
        yield StreamChunk(
            type=config.chunk_type,
            status=config.status_called,
            content=f"{config.emoji_prefix} Calling {tool_name}...",
            source=f"{config.source_prefix}{tool_name}",
            tool_call_id=call_id,
        )

        yield StreamChunk(
            type=config.chunk_type,
            status="function_call",
            content=f"Arguments for Calling {tool_name}: {arguments_str}",
            source=f"{config.source_prefix}{tool_name}",
            tool_call_id=call_id,
            display=False,  # Verbose diagnostic - shown in tool card instead
        )

        request = self._build_nlip_request(call)
        call_descriptor = "MCP call" if config.tool_type == "mcp" else "custom tool call"
        call_reference = f" (id {call_id})" if call_id else ""
        transfer_message = f"🔁 [NLIP Router] Transferring {call_descriptor} '{tool_name}' via NLIP router{call_reference}"
        logger.info(
            f"[NLIP] Routing {call_descriptor} '{tool_name}'{call_reference} through NLIP router",
        )
        yield StreamChunk(
            type=config.chunk_type,
            status="nlip_transfer",
            content=transfer_message,
            source=f"{config.source_prefix}{tool_name}",
            tool_call_id=call_id,
        )

        # Properly handle the async generator to avoid GeneratorExit issues
        nlip_generator = self._nlip_router.route_message(request)
        result_found = False

        try:
            async for response in nlip_generator:
                chunk = self._convert_nlip_stream_chunk(
                    response.content,
                    config,
                    tool_name,
                )
                if chunk:
                    yield chunk
                    continue

                if response.tool_results:
                    matching_result = self._select_matching_tool_result(
                        response.tool_results,
                        call_id,
                    )
                    if not matching_result:
                        continue

                    if matching_result.status == "error":
                        error_msg = matching_result.error or "Unknown error"
                        self._append_tool_error_message(
                            updated_messages,
                            call,
                            error_msg,
                            config.tool_type,
                        )
                        processed_call_ids.add(call_id)
                        yield StreamChunk(
                            type=config.chunk_type,
                            status=config.status_error,
                            content=f"{config.error_emoji} {tool_name}: {error_msg}",
                            source=f"{config.source_prefix}{tool_name}",
                            tool_call_id=call_id,
                        )
                        result_found = True
                        break

                    result_text = self._extract_nlip_result_text(
                        matching_result,
                        config.tool_type,
                    )
                    self._append_tool_result_message(
                        updated_messages,
                        call,
                        result_text,
                        config.tool_type,
                    )
                    processed_call_ids.add(call_id)

                    yield StreamChunk(
                        type=config.chunk_type,
                        status="function_call_output",
                        content=f"Results for Calling {tool_name}: {result_text}",
                        source=f"{config.source_prefix}{tool_name}",
                        tool_call_id=call_id,
                        display=False,  # Verbose diagnostic - shown in tool card instead
                    )

                    yield StreamChunk(
                        type=config.chunk_type,
                        status=config.status_response,
                        content=f"{config.success_emoji} {tool_name} completed",
                        source=f"{config.source_prefix}{tool_name}",
                        tool_call_id=call_id,
                    )
                    result_found = True
                    break
        finally:
            # Ensure the async generator is properly closed
            if hasattr(nlip_generator, "aclose"):
                try:
                    await nlip_generator.aclose()
                except Exception as close_error:
                    logger.debug(f"Error closing NLIP generator: {close_error}")

        if not result_found:
            raise Exception("NLIP router returned no result")

    def _convert_nlip_stream_chunk(
        self,
        content: dict[str, Any] | None,
        config: ToolExecutionConfig,
        tool_name: str,
    ) -> StreamChunk | None:
        """Convert NLIP streaming payload into a StreamChunk."""
        if not content:
            logger.debug(f"[NLIP] No content in stream chunk for {tool_name}")
            return None

        stream_data = content.get("stream_chunk")
        if not stream_data:
            logger.debug(f"[NLIP] Missing stream_chunk entry for {tool_name}")
            return None

        if isinstance(stream_data, bytes):
            content_str = stream_data.decode("utf-8", errors="replace")
        elif isinstance(stream_data, (dict, list)):
            content_str = json.dumps(stream_data)
            if len(content_str) > 10000:
                logger.warning(
                    f"[NLIP] Large stream chunk ({len(content_str)} chars) for {tool_name}",
                )
                content_str = f"{content_str[:10000]}...[truncated]"
        else:
            content_str = str(stream_data)

        status = "custom_tool_output" if config.tool_type == "custom" else "mcp_tool_output"
        return StreamChunk(
            type=config.chunk_type,
            status=status,
            content=content_str,
            source=f"{config.source_prefix}{tool_name}",
        )

    @staticmethod
    def _select_matching_tool_result(
        tool_results: list[Any],
        call_id: str,
    ) -> Any | None:
        """Return the NLIPToolResult that matches the requested call_id."""
        if not tool_results:
            logger.error("[NLIP] No tool results available for selection")
            return None

        if not call_id:
            logger.warning(
                "[NLIP] No call_id provided for tool result selection; defaulting to first result",
            )
            return tool_results[0]

        for result in tool_results:
            if result.tool_id == call_id:
                return result

        available_ids = [result.tool_id for result in tool_results]
        logger.error(
            f"[NLIP] No tool result matched call_id={call_id}. " f"Available IDs: {available_ids}. Using first entry as fallback.",
        )
        return tool_results[0]

    def _extract_nlip_result_text(self, tool_result: Any, tool_type: str) -> str:
        """Extract human-readable text from NLIP tool results."""
        raw_result = tool_result.result
        tool_name = getattr(tool_result, "tool_name", "unknown_tool")

        if isinstance(raw_result, str):
            logger.debug(
                f"[NLIP] Extracted string result for {tool_name} ({len(raw_result)} chars)",
            )
            return raw_result

        if isinstance(raw_result, dict) and "output" in raw_result:
            output = str(raw_result["output"])
            logger.debug(
                f"[NLIP] Extracted dict['output'] result for {tool_name} ({len(output)} chars)",
            )
            return output

        # Handle MCP CallToolResult objects (has .content attribute)
        if hasattr(raw_result, "content") and not isinstance(raw_result, dict):
            content_payload = getattr(raw_result, "content", None)
            content_text = self._extract_text_from_content(content_payload)
            if content_text:
                logger.debug(
                    f"[NLIP] Extracted CallToolResult.content for {tool_name} ({len(content_text)} chars)",
                )
                return content_text

        if isinstance(raw_result, (dict, list)):
            content_payload = raw_result.get("content") if isinstance(raw_result, dict) else raw_result
            content_text = self._extract_text_from_content(content_payload)
            if content_text:
                logger.debug(
                    f"[NLIP] Extracted MCP-style content result for {tool_name} ({len(content_text)} chars)",
                )
                return content_text

        if raw_result is None:
            logger.warning(f"[NLIP] Tool {tool_name} returned None result")
            return ""

        logger.warning(
            f"[NLIP] Falling back to stringified {type(raw_result).__name__} result " f"for {tool_name}",
        )
        fallback = json.dumps(raw_result, indent=2, ensure_ascii=False) if isinstance(raw_result, (dict, list)) else str(raw_result)
        return fallback

    @staticmethod
    def _extract_text_from_content(content: Any) -> str | None:
        """Extract text from MCP-style content payload."""
        if not content:
            return None

        if isinstance(content, list):
            text_parts = []
            for item in content:
                # Handle MCP TextContent objects (have .text attribute)
                if hasattr(item, "text"):
                    text_parts.append(str(item.text))
                # Handle dict-based content
                elif isinstance(item, dict):
                    if "text" in item:
                        text_parts.append(str(item["text"]))
                    elif "type" in item and item["type"] == "text" and "content" in item:
                        text_parts.append(str(item["content"]))
                elif isinstance(item, str):
                    text_parts.append(item)
            return "\n".join(text_parts) if text_parts else None

        if isinstance(content, dict):
            if "text" in content:
                return str(content["text"])
            if "content" in content:
                return CustomToolAndMCPBackend._extract_text_from_content(
                    content["content"],
                )

        if isinstance(content, str):
            return content

        return None

    # MCP support methods
    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client for mcp_tools-based servers (stdio + streamable-http)."""
        if not self.mcp_servers or self._mcp_initialized:
            return

        try:
            # Normalize and separate MCP servers by transport type using mcp_tools utilities
            normalized_servers = (
                MCPSetupManager.normalize_mcp_servers(
                    self.mcp_servers,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
                if MCPSetupManager
                else []
            )

            if not MCPSetupManager:
                logger.warning("MCPSetupManager not available")
                return

            mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
                normalized_servers,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

            if not mcp_tools_servers:
                logger.info("No stdio/streamable-http servers configured")
                return

            # Apply circuit breaker filtering before connection attempts
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker and MCPCircuitBreakerManager:
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    mcp_tools_servers,
                    self._mcp_tools_circuit_breaker,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
                if not filtered_servers:
                    logger.warning(
                        "All MCP servers blocked by circuit breaker during setup",
                    )
                    return
                if len(filtered_servers) < len(mcp_tools_servers):
                    logger.info(
                        f"Circuit breaker filtered {len(mcp_tools_servers) - len(filtered_servers)} servers during setup",
                    )
                servers_to_use = filtered_servers
            else:
                servers_to_use = mcp_tools_servers

            # Setup MCP client using consolidated utilities
            if not MCPResourceManager:
                logger.warning("MCPResourceManager not available")
                return

            self._mcp_client = await MCPResourceManager.setup_mcp_client(
                servers=servers_to_use,
                allowed_tools=self.allowed_tools,
                exclude_tools=self.exclude_tools,
                circuit_breaker=self._mcp_tools_circuit_breaker,
                timeout_seconds=400,  # Increased timeout for image generation tools
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

            # Guard after client setup
            if not self._mcp_client:
                self._mcp_initialized = False
                logger.warning(
                    "MCP client setup failed, falling back to no-MCP streaming",
                )
                return

            # Convert tools to functions using consolidated utility
            self._mcp_functions.update(
                MCPResourceManager.convert_tools_to_functions(
                    self._mcp_client,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                    hook_manager=getattr(self, "function_hook_manager", None),
                    backend=self,  # Pass backend for round tracking context
                ),
            )

            # Setup code-based tools if enabled (CodeAct paradigm)
            if self.filesystem_manager and self.filesystem_manager.enable_code_based_tools:
                # Filter out user MCP tools from protocol access (they're accessible via code)
                # Framework MCPs (from FRAMEWORK_MCPS constant) and direct_mcp_servers remain as protocol tools

                # Get direct MCP servers from filesystem manager (user-specified servers to keep as protocol tools)
                direct_mcps = set(getattr(self.filesystem_manager, "direct_mcp_servers", []) or [])

                # Remove user MCP tools from _mcp_functions
                filtered_functions = {}
                removed_tools = []
                for tool_name, function in self._mcp_functions.items():
                    # Get server name from tool name (format: server__tool or just tool)
                    server_name = self._mcp_client._tool_to_server.get(tool_name) if self._mcp_client else None

                    # Check if server is a framework MCP (exact match or prefix match like "planning_agent_a")
                    is_framework_mcp = server_name and (server_name in FRAMEWORK_MCPS or any(server_name.startswith(f"{fmcp}_") for fmcp in FRAMEWORK_MCPS))

                    # Check if server is a user-specified direct MCP (keep as protocol tool)
                    is_direct_mcp = server_name in direct_mcps

                    if is_framework_mcp or is_direct_mcp:
                        filtered_functions[tool_name] = function
                    elif not server_name:
                        # Unknown server, keep it to be safe
                        filtered_functions[tool_name] = function
                    else:
                        removed_tools.append(tool_name)

                if removed_tools:
                    logger.info(
                        f"[MCP] Filtered out user MCP tools (accessible via code): {removed_tools}",
                    )

                self._mcp_functions = filtered_functions
                try:
                    logger.info("[MCP] Setting up code-based tools from MCP client")
                    await self.filesystem_manager.setup_code_based_tools_from_mcp_client(
                        self._mcp_client,
                    )
                except Exception as e:
                    logger.error(
                        f"[MCP] Failed to setup code-based tools: {e}",
                        exc_info=True,
                    )
                    # Don't fail MCP setup if code generation fails
                    # Agent can still use protocol-based tools

            self._mcp_initialized = True
            logger.info(
                f"Successfully initialized MCP sessions with {len(self._mcp_functions)} tools converted to functions",
            )

            # Record success for circuit breaker
            await self._record_mcp_circuit_breaker_success(servers_to_use)

        except Exception as e:
            # Record failure for circuit breaker
            self._record_mcp_circuit_breaker_failure(e, self.agent_id)
            logger.warning(f"Failed to setup MCP sessions: {e}")
            self._mcp_client = None
            self._mcp_initialized = False
            self._mcp_functions = {}

    async def _execute_mcp_function_with_retry(
        self,
        function_name: str,
        arguments_json: str,
        max_retries: int = 3,
    ) -> tuple[str, Any]:
        """Execute MCP function with exponential backoff retry logic."""
        # Check if this specific MCP tool is blocked by planning mode
        if self.is_mcp_tool_blocked(function_name):
            logger.info(
                f"[MCP] Planning mode enabled - blocking MCP tool: {function_name}",
            )
            error_str = f"🚫 [MCP] Tool '{function_name}' blocked during coordination (planning mode active)"
            return error_str, {
                "error": error_str,
                "blocked_by": "planning_mode",
                "function_name": function_name,
            }

        # Convert JSON string to dict for shared utility
        try:
            args, decode_passes = normalize_json_object_argument(
                arguments_json,
                field_name="arguments",
            )
        except ValueError as e:
            error_str = f"Error: {e}"
            return error_str, {"error": error_str}
        if decode_passes > 1:
            logger.info(
                "[MCP] Normalized %s decode passes for %s arguments",
                decode_passes,
                function_name,
            )

        # Stats callback for tracking
        async def stats_callback(action: str) -> int:
            async with self._stats_lock:
                if action == "increment_calls":
                    self._mcp_tool_calls_count += 1
                    return self._mcp_tool_calls_count
                elif action == "increment_failures":
                    self._mcp_tool_failures += 1
                    return self._mcp_tool_failures
            return 0

        # Circuit breaker callback
        async def circuit_breaker_callback(event: str, error_msg: str = "") -> None:
            if not (self._circuit_breakers_enabled and MCPCircuitBreakerManager and self._mcp_tools_circuit_breaker):
                return

            # For individual function calls, we don't have server configurations readily available
            # The circuit breaker manager should handle this gracefully with empty server list
            if event == "failure":
                await MCPCircuitBreakerManager.record_event(
                    [],
                    self._mcp_tools_circuit_breaker,
                    "failure",
                    error_msg,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
            else:
                await MCPCircuitBreakerManager.record_event(
                    [],
                    self._mcp_tools_circuit_breaker,
                    "success",
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )

        if not MCPExecutionManager:
            return "Error: MCPExecutionManager unavailable", {
                "error": "MCPExecutionManager unavailable",
            }

        result = await MCPExecutionManager.execute_function_with_retry(
            function_name=function_name,
            args=args,
            functions=self._mcp_functions,
            max_retries=max_retries,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger,
        )

        # Convert result to string for compatibility and return tuple
        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}", result

        # Note: Reminder injection happens in _execute_tool_with_logging, not here
        return str(result), result

    async def _process_upload_files(
        self,
        messages: list[dict[str, Any]],
        all_params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Process upload_files config entries and attach to messages.

        Supports these forms:

        - {"image_path": "..."}: image file path or HTTP/HTTPS URL
          - Local paths: loads and base64-encodes the image file
          - URLs: passed directly without encoding
          Supported formats: PNG, JPEG, WEBP, GIF, BMP, TIFF, HEIC (provider-dependent)

        - {"audio_path": "..."}: audio file path or HTTP/HTTPS URL
          - Local paths: loads and base64-encodes the audio file
          - URLs: fetched and base64-encoded (30s timeout, configurable size limit)
          Supported formats: WAV, MP3 (strictly validated)

        - {"video_path": "..."}: video file path or HTTP/HTTPS URL
          - Local paths: loads and base64-encodes the video file
          - URLs: passed directly without encoding, converted to video_url format
          Supported formats: MP4, AVI, MOV, WEBM (provider-dependent)

        - {"file_path": "..."}: document/code file for File Search (local path or URL)
          - Local paths: validated against supported extensions and size limits
          - URLs: queued for upload without local validation
          Supported extensions: .c, .cpp, .cs, .css, .doc, .docx, .html, .java, .js,
          .json, .md, .pdf, .php, .pptx, .py, .rb, .sh, .tex, .ts, .txt

        Note: Format support varies by provider (OpenAI, Qwen, vLLM, etc.). The implementation
        uses MIME type detection for automatic format handling.

        Audio/Video/Image uploads are limited by `media_max_file_size_mb` (default 64MB).
        File Search files are limited to 512MB. You can override limits via config or call parameters.

        Returns updated messages list with additional content items.
        """

        upload_entries = all_params.get("upload_files")
        if not upload_entries:
            return messages

        if not self.supports_upload_files():
            logger.debug(
                "upload_files provided but backend %s does not support file uploads; ignoring",
                self.get_provider_name(),
            )
            all_params.pop("upload_files", None)
            return messages

        processed_messages = list(messages)
        extra_content: list[dict[str, Any]] = []
        has_file_search_files = False

        for entry in upload_entries:
            if not isinstance(entry, dict):
                logger.warning("upload_files entry is not a dict: %s", entry)
                raise UploadFileError("Each upload_files entry must be a mapping")

            # Check for file_path (File Search documents/code)
            file_path_value = entry.get("file_path")
            if file_path_value:
                # Process file_path entry for File Search
                file_content = self._process_file_path_entry(
                    file_path_value,
                    all_params,
                )
                if file_content:
                    extra_content.append(file_content)
                    has_file_search_files = True
                continue

            # Check for image_path (supports both URLs and local paths)
            # image_url deprecated; use image_path with http(s) URL instead
            path_value = entry.get("image_path")

            if path_value:
                # Check if it's a URL (like file_path does)
                if path_value.startswith(("http://", "https://")):
                    # Handle image URLs directly (no base64 encoding needed)
                    extra_content.append(
                        {
                            "type": "image",
                            "url": path_value,
                        },
                    )
                else:
                    # Handle local file paths
                    resolved = self._resolve_local_path(path_value, all_params)

                    if not resolved.exists():
                        raise UploadFileError(f"File not found: {resolved}")

                    # Enforce configurable media size limit (in MB) for images (parity with audio/video)
                    limit_mb = all_params.get("media_max_file_size_mb") or self.config.get("media_max_file_size_mb") or MEDIA_MAX_FILE_SIZE_MB
                    self._validate_media_size(resolved, int(limit_mb))

                    encoded, mime_type = self._read_base64(resolved)
                    if not mime_type:
                        mime_type = "image/jpeg"

                    extra_content.append(
                        {
                            "type": "image",
                            "base64": encoded,
                            "mime_type": mime_type,
                            "source_path": str(resolved),
                        },
                    )

                continue

            audio_path_value = entry.get("audio_path")

            if audio_path_value:
                # Check if it's a URL (like file_path does)
                if audio_path_value.startswith(("http://", "https://")):
                    # Fetch audio URL and convert to base64
                    encoded, mime_type = await self._fetch_audio_url_as_base64(
                        audio_path_value,
                        all_params,
                    )
                    extra_content.append(
                        {
                            "type": "audio",
                            "base64": encoded,
                            "mime_type": mime_type,
                        },
                    )
                else:
                    # Handle local file paths
                    resolved = self._resolve_local_path(audio_path_value, all_params)

                    if not resolved.exists():
                        raise UploadFileError(f"Audio file not found: {resolved}")

                    # Enforce configurable media size limit (in MB)
                    limit_mb = all_params.get("media_max_file_size_mb") or self.config.get("media_max_file_size_mb") or MEDIA_MAX_FILE_SIZE_MB

                    self._validate_media_size(resolved, int(limit_mb))

                    encoded, mime_type = self._read_base64(resolved)

                    # Validate audio format (wav and mp3 only)
                    mime_lower = (mime_type or "").split(";")[0].strip().lower()
                    if mime_lower not in SUPPORTED_AUDIO_MIME_TYPES:
                        raise UploadFileError(
                            f"Unsupported audio format for {resolved}. " f"Supported formats: mp3, wav",
                        )

                    # Normalize MIME type
                    if mime_lower in {"audio/wav", "audio/wave", "audio/x-wav"}:
                        mime_type = "audio/wav"
                    else:
                        mime_type = "audio/mpeg"

                    extra_content.append(
                        {
                            "type": "audio",
                            "base64": encoded,
                            "mime_type": mime_type,
                            "source_path": str(resolved),
                        },
                    )

                continue

            # Check for video_path (supports both URLs and local paths)
            video_path_value = entry.get("video_path")

            if video_path_value:
                # Check if it's a URL
                if video_path_value.startswith(("http://", "https://")):
                    # Handle video URLs directly (no base64 encoding needed)
                    extra_content.append(
                        {
                            "type": "video_url",
                            "url": video_path_value,
                        },
                    )
                else:
                    # Handle local file paths
                    resolved = self._resolve_local_path(video_path_value, all_params)

                    if not resolved.exists():
                        raise UploadFileError(f"Video file not found: {resolved}")

                    # Enforce configurable media size limit (in MB)
                    limit_mb = all_params.get("media_max_file_size_mb") or self.config.get("media_max_file_size_mb") or MEDIA_MAX_FILE_SIZE_MB

                    self._validate_media_size(resolved, int(limit_mb))

                    encoded, mime_type = self._read_base64(resolved)
                    if not mime_type:
                        mime_type = "video/mp4"
                    extra_content.append(
                        {
                            "type": "video",
                            "base64": encoded,
                            "mime_type": mime_type,
                            "source_path": str(resolved),
                        },
                    )

                continue

            raise UploadFileError(
                "upload_files entry must specify either 'image_path', 'audio_path', 'video_path', or 'file_path'",
            )

        if not extra_content:
            return processed_messages

        # Track if file search files are present for API params handler
        if has_file_search_files:
            all_params["_has_file_search_files"] = True

        if processed_messages:
            last_message = processed_messages[-1].copy()
            last_content = last_message.get("content", [])

            if isinstance(last_content, str):
                last_content = [{"type": "text", "text": last_content}]
            elif isinstance(last_content, dict) and "type" in last_content:
                last_content = [dict(last_content)]
            elif isinstance(last_content, list):
                if all(isinstance(item, str) for item in last_content):
                    last_content = [{"type": "text", "text": item} for item in last_content]
                elif all(isinstance(item, dict) and "type" in item and "text" in item for item in last_content):
                    last_content = list(last_content)
                else:
                    last_content = []
            else:
                last_content = []

            last_content.extend(extra_content)
            last_message["content"] = last_content
            processed_messages[-1] = last_message
        else:
            processed_messages.append(
                {
                    "role": "user",
                    "content": extra_content,
                },
            )

        # Prevent downstream handlers from seeing upload_files
        all_params.pop("upload_files", None)

        return processed_messages

    def _process_file_path_entry(
        self,
        file_path_value: str,
        all_params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Process file path entry and validate against provider-specific restrictions.

        Note: This base implementation validates against OpenAI File Search extensions.
        Backends like Claude may have additional restrictions (e.g., only .pdf and .txt)
        and should perform provider-specific validation in their upload methods.
        """
        # Check if it's a URL
        if file_path_value.startswith(("http://", "https://")):
            logger.info(f"Queued file URL for File Search upload: {file_path_value}")
            return {
                "type": "file_pending_upload",
                "url": file_path_value,
                "source": "url",
            }

        # Local file path
        resolved = Path(file_path_value).expanduser()
        if not resolved.is_absolute():
            cwd = all_params.get("cwd") or self.config.get("cwd")
            if cwd:
                resolved = Path(cwd).joinpath(resolved)
            else:
                resolved = resolved.resolve()

        if not resolved.exists():
            raise UploadFileError(f"File not found: {resolved}")

        # Validate file extension (OpenAI File Search extensions)
        # Note: Backends like Claude may override with stricter validation
        file_ext = resolved.suffix.lower()
        if file_ext not in FILE_SEARCH_SUPPORTED_EXTENSIONS:
            raise UploadFileError(
                f"File type {file_ext} not supported by File Search. " f"Supported types: {', '.join(sorted(FILE_SEARCH_SUPPORTED_EXTENSIONS))}",
            )

        # Validate file size
        file_size = resolved.stat().st_size
        if file_size > FILE_SEARCH_MAX_FILE_SIZE:
            raise UploadFileError(
                f"File size {file_size / (1024*1024):.2f} MB exceeds " f"File Search limit of {FILE_SEARCH_MAX_FILE_SIZE / (1024*1024):.0f} MB",
            )

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(resolved.as_posix())
        if not mime_type:
            mime_type = "application/octet-stream"

        logger.info(f"Queued local file for File Search upload: {resolved}")
        return {
            "type": "file_pending_upload",
            "path": str(resolved),
            "mime_type": mime_type,
            "source": "local",
        }

    def _resolve_local_path(self, raw_path: str, all_params: dict[str, Any]) -> Path:
        """Resolve a local path using cwd from all_params or config, mirroring file_path resolution."""
        resolved = Path(raw_path).expanduser()
        if not resolved.is_absolute():
            cwd = all_params.get("cwd") or self.config.get("cwd")
            if cwd:
                resolved = Path(cwd).joinpath(resolved)
            else:
                resolved = resolved.resolve()
        return resolved

    def _validate_media_size(self, path: Path, limit_mb: int) -> None:
        """Validate media file size against MB limit; raise UploadFileError if exceeded."""
        file_size = path.stat().st_size
        if file_size > limit_mb * 1024 * 1024:
            logger.warning(
                f"Media file too large: {file_size / (1024 * 1024):.2f} MB at {path} (limit {limit_mb} MB)",
            )
            raise UploadFileError(
                f"Media file size {file_size / (1024 * 1024):.2f} MB exceeds limit of {limit_mb:.0f} MB: {path}",
            )

    def _read_base64(self, path: Path) -> tuple[str, str]:
        """Read file bytes and return (base64, guessed_mime_type)."""
        mime_type, _ = mimetypes.guess_type(path.as_posix())
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise UploadFileError(f"Failed to read file {path}: {exc}") from exc
        encoded = base64.b64encode(data).decode("utf-8")
        return encoded, (mime_type or "")

    async def _fetch_audio_url_as_base64(
        self,
        url: str,
        all_params: dict[str, Any],
    ) -> tuple[str, str]:
        """
        Fetch audio from URL and return (base64_encoded_data, mime_type).

        Currently supports: wav, mp3

        Args:
            url: HTTP/HTTPS URL to fetch audio from
            all_params: Parameters dict containing optional media_max_file_size_mb

        Returns:
            Tuple of (base64_encoded_string, mime_type)

        Raises:
            UploadFileError: If fetch fails, format is unsupported, or size exceeds limit
        """
        # Get size limit from config (default 64MB)
        limit_mb = all_params.get("media_max_file_size_mb") or self.config.get("media_max_file_size_mb") or MEDIA_MAX_FILE_SIZE_MB
        max_size_bytes = int(limit_mb) * 1024 * 1024

        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(url, timeout=30.0)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise UploadFileError(
                    f"Timeout (30s) while fetching audio from {url}",
                ) from exc
            except httpx.HTTPError as exc:
                raise UploadFileError(
                    f"Failed to fetch audio from {url}: {exc}",
                ) from exc

            # Validate Content-Type
            content_type = response.headers.get("Content-Type", "")
            mime_type = content_type.split(";")[0].strip().lower()

            # Simple format validation (wav and mp3 only)
            if mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
                # Try to guess from URL extension
                guessed_mime, _ = mimetypes.guess_type(url)
                if guessed_mime and guessed_mime.lower() in SUPPORTED_AUDIO_MIME_TYPES:
                    mime_type = guessed_mime.lower()
                else:
                    raise UploadFileError(
                        f"Unsupported audio format for {url}. " f"Supported formats: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}",
                    )

            # Normalize MIME type
            if mime_type in {"audio/wav", "audio/wave", "audio/x-wav"}:
                mime_type = "audio/wav"
            elif mime_type in {"audio/mpeg", "audio/mp3"}:
                mime_type = "audio/mpeg"

            # Get audio bytes
            audio_bytes = response.content

            # Validate size
            if len(audio_bytes) > max_size_bytes:
                raise UploadFileError(
                    f"Audio file size {len(audio_bytes) / (1024 * 1024):.2f} MB exceeds limit of {limit_mb} MB: {url}",
                )

            # Encode to base64
            encoded = base64.b64encode(audio_bytes).decode("utf-8")

            logger.info(
                f"Fetched and encoded audio from URL: {url} " f"({len(audio_bytes) / (1024 * 1024):.2f} MB, {mime_type})",
            )

            return encoded, mime_type

    async def _compress_messages_for_context_recovery(
        self,
        messages: list[dict[str, Any]],
        buffer_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """Compress messages for context error recovery.

        Default implementation that subclasses inherit automatically.
        Subclasses can override if they need custom compression logic.

        Args:
            messages: The messages that caused the context length error
            buffer_content: Optional partial response content from streaming buffer

        Returns:
            Compressed message list ready for retry
        """
        from ._compression_utils import compress_messages_for_recovery

        logger.info(
            f"[{self.get_provider_name()}] Compressing {len(messages)} messages " f"with target_ratio={self._compression_target_ratio}",
        )

        result = await compress_messages_for_recovery(
            messages=messages,
            backend=self,
            target_ratio=self._compression_target_ratio,
            buffer_content=buffer_content,
        )

        logger.info(
            f"[{self.get_provider_name()}] Compressed {len(messages)} messages " f"to {len(result)} messages",
        )

        return result

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""

        agent_id = kwargs.get("agent_id", None)

        # Load task context from CONTEXT.md if it exists (for multimodal tools and subagents)
        task_context = None
        if self.filesystem_manager and self.filesystem_manager.cwd:
            from massgen.context.task_context import load_task_context

            # Load context if available, but don't require it here (tools will require it)
            task_context = load_task_context(
                str(self.filesystem_manager.cwd),
                required=False,
            )

        # Build execution context for tools (generic, not tool-specific)
        self._execution_context = ExecutionContext(
            messages=messages,
            agent_system_message=kwargs.get("system_message", None),
            agent_id=agent_id or self.agent_id,  # Use kwargs agent_id, fallback to instance attribute
            backend_name=self.backend_name,
            backend_type=normalize_backend_type(self.get_provider_name()),  # For multimodal capability lookup
            model=kwargs.get(
                "model",
                "",
            ),  # For model-specific multimodal capability lookup
            current_stage=self.coordination_stage,
            # Workspace context for file operations and multimodal tools
            agent_cwd=str(self.filesystem_manager.cwd) if self.filesystem_manager else None,
            allowed_paths=(
                self.filesystem_manager.path_permission_manager.get_mcp_filesystem_paths()
                if self.filesystem_manager and hasattr(self.filesystem_manager, "path_permission_manager") and self.filesystem_manager.path_permission_manager
                else None
            ),
            multimodal_config=self._multimodal_config if hasattr(self, "_multimodal_config") else None,
            task_context=task_context,
        )

        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Catch setup errors by wrapping the context manager itself
        try:
            # Use async context manager for proper MCP resource management
            async with self:
                client = self._create_client(**kwargs)

                try:
                    # Determine if MCP processing is needed
                    use_mcp = bool(self._mcp_functions)

                    # Use parent class method to yield MCP status chunks
                    async for chunk in self.yield_mcp_status_chunks(use_mcp):
                        yield chunk

                    use_custom_tools = bool(self._custom_tool_names)

                    if use_mcp or use_custom_tools:
                        # MCP MODE: Recursive function call detection and execution
                        logger.info("Using recursive MCP execution mode")

                        current_messages = self._trim_message_history(messages.copy())

                        # Start recursive MCP streaming
                        async for chunk in self._stream_with_custom_and_mcp_tools(
                            current_messages,
                            tools,
                            client,
                            **kwargs,
                        ):
                            yield chunk

                    else:
                        # NON-MCP MODE: Simple passthrough streaming
                        logger.info("Using no-MCP mode")

                        # Start non-MCP streaming
                        async for chunk in self._stream_without_custom_and_mcp_tools(
                            messages,
                            tools,
                            client,
                            **kwargs,
                        ):
                            yield chunk

                except Exception as e:
                    # Enhanced error handling for MCP-related errors during streaming
                    if isinstance(
                        e,
                        (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError),
                    ):
                        # Record failure for circuit breaker
                        await self._record_mcp_circuit_breaker_failure(e, agent_id)

                        # Handle MCP exceptions with fallback
                        async for chunk in self._stream_handle_custom_and_mcp_exceptions(
                            e,
                            messages,
                            tools,
                            client,
                            **kwargs,
                        ):
                            yield chunk
                    else:
                        # Check if this is a context length error that we can recover from
                        from ._context_errors import is_context_length_error

                        _compression_retry = kwargs.get("_compression_retry", False)

                        if is_context_length_error(e) and not _compression_retry and hasattr(self, "_compress_messages_for_context_recovery"):
                            logger.warning(
                                f"[{self.get_provider_name()}] Context length exceeded during streaming, " f"attempting compression recovery...",
                            )
                            try:
                                agent_id = kwargs.get("agent_id")

                                # Notify user that compression is starting
                                yield StreamChunk(
                                    type="compression_status",
                                    status="compressing",
                                    content=f"\n📦 [Compression] Context limit exceeded - summarizing {len(messages)} messages...",
                                    source=agent_id,
                                )

                                # Get streaming buffer content if available (subclass may track this)
                                buffer_content = getattr(self, "_streaming_buffer", None) or None

                                # Compress messages using LLM-based summarization
                                compressed_messages = await self._compress_messages_for_context_recovery(
                                    messages,
                                    buffer_content=buffer_content,
                                )

                                # Notify user that compression succeeded
                                input_count = len(compressed_messages) if compressed_messages else 0
                                result_msg = f"✅ [Compression] Recovered via summarization ({input_count} items) - continuing..."
                                yield StreamChunk(
                                    type="compression_status",
                                    status="compression_complete",
                                    content=result_msg,
                                    source=agent_id,
                                )

                                # Retry with compressed messages (with flag to prevent infinite loops)
                                # Remove previous_response_id - it would add all prior context server-side,
                                # making compression pointless
                                retry_kwargs = {**kwargs, "_compression_retry": True}
                                retry_kwargs.pop("previous_response_id", None)

                                if use_mcp or use_custom_tools:
                                    async for chunk in self._stream_with_custom_and_mcp_tools(
                                        compressed_messages,
                                        tools,
                                        client,
                                        **retry_kwargs,
                                    ):
                                        yield chunk
                                else:
                                    async for chunk in self._stream_without_custom_and_mcp_tools(
                                        compressed_messages,
                                        tools,
                                        client,
                                        **retry_kwargs,
                                    ):
                                        yield chunk

                                logger.info(
                                    f"[{self.get_provider_name()}] Compression recovery successful",
                                )
                            except Exception as retry_error:
                                # Save retry input to debug folder for analysis
                                from ..backend._compression_utils import (
                                    save_retry_input_debug,
                                )

                                save_retry_input_debug(
                                    compressed_messages,
                                    tools,
                                    error=str(retry_error),
                                )
                                logger.error(
                                    f"Compression recovery failed: {retry_error}",
                                    exc_info=True,
                                )
                                yield StreamChunk(
                                    type="error",
                                    error=f"Compression recovery failed: {type(retry_error).__name__}: {retry_error}",
                                )
                        else:
                            # Check if this is the known "response.completed" error from OpenAI SDK/Logfire
                            # This happens when streams end early (e.g., after tool execution) - it's recoverable
                            if "response.completed" in str(e):
                                # Track incomplete response recovery attempts
                                self._incomplete_response_count += 1

                                # Get the streaming buffer content if available
                                buffer_content = None
                                if hasattr(self, "_get_streaming_buffer"):
                                    buffer_content = self._get_streaming_buffer()

                                # Get agent_id for logging
                                agent_id = kwargs.get("agent_id")

                                # Check retry limit (default 5)
                                max_incomplete_retries = getattr(self, "_max_incomplete_response_retries", 5)

                                # Log with Logfire span for visibility
                                with logfire.span(
                                    "incomplete_response_recovery",
                                    attempt=self._incomplete_response_count,
                                    max_attempts=max_incomplete_retries,
                                    buffer_size=len(buffer_content or ""),
                                    agent_id=agent_id,
                                ):
                                    logger.warning(
                                        f"[IncompleteResponse] Recovery attempt {self._incomplete_response_count}/{max_incomplete_retries} - "
                                        f"preserved {len(buffer_content or '')} chars of streamed content",
                                    )

                                if self._incomplete_response_count > max_incomplete_retries:
                                    logger.error(
                                        f"[IncompleteResponse] Max retries ({max_incomplete_retries}) exceeded",
                                    )
                                    yield StreamChunk(
                                        type="error",
                                        error=f"Max incomplete response retries ({max_incomplete_retries}) exceeded. " f"The API stream ended prematurely {self._incomplete_response_count} times.",
                                    )
                                else:
                                    # Yield a special chunk to signal incomplete response recovery
                                    # The orchestrator will continue with the existing context
                                    # Note: Buffer content has already been streamed and is in the conversation history
                                    yield StreamChunk(
                                        type="incomplete_response_recovery",
                                        content=buffer_content,
                                        source=agent_id,
                                        detail=f"Recovery attempt {self._incomplete_response_count}/{max_incomplete_retries}",
                                    )
                                    # Don't yield error chunk - this is recoverable
                                    # The streaming loop will continue and make a new API call
                            else:
                                logger.error(f"Streaming error: {e}")
                                yield StreamChunk(type="error", error=str(e))

                finally:
                    await self._cleanup_client(client)
        except Exception as e:
            # Handle exceptions that occur during MCP setup (__aenter__) or teardown
            # Provide a clear user-facing message and fall back to non-MCP streaming
            client = None

            try:
                client = self._create_client(**kwargs)

                if isinstance(
                    e,
                    (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError),
                ):
                    # Handle MCP exceptions with fallback
                    async for chunk in self._stream_handle_custom_and_mcp_exceptions(
                        e,
                        messages,
                        tools,
                        client,
                        **kwargs,
                    ):
                        yield chunk
                else:
                    # Generic setup error: still notify if MCP was configured
                    if self.mcp_servers:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            source="mcp_setup",
                        )

                    # Proceed with non-MCP streaming
                    async for chunk in self._stream_without_custom_and_mcp_tools(
                        messages,
                        tools,
                        client,
                        **kwargs,
                    ):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                # Save streaming buffer before cleanup
                if hasattr(self, "_finalize_streaming_buffer"):
                    self._finalize_streaming_buffer(agent_id=agent_id)
                await self._cleanup_client(client)

    @abstractmethod
    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        yield StreamChunk(type="error", error="Not implemented")

    @abstractmethod
    def _create_client(self, **kwargs):
        pass

    async def _stream_without_custom_and_mcp_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Simple passthrough streaming without MCP processing."""

        # Extract internal flags before merging kwargs (prevents API errors from unknown params)
        kwargs.pop("_compression_retry", None)

        agent_id = kwargs.get("agent_id", None)
        all_params = {**self.config, **kwargs}
        processed_messages = await self._process_upload_files(messages, all_params)
        api_params = await self.api_params_handler.build_api_params(
            processed_messages,
            tools,
            all_params,
        )

        # Remove any MCP tools from the tools list
        if "tools" in api_params:
            non_mcp_tools = []
            for tool in api_params.get("tools", []):
                # Check different formats for MCP tools
                if tool.get("type") == "function":
                    name = tool.get("function", {}).get("name") if "function" in tool else tool.get("name")
                    if name and name in self._mcp_function_names:
                        continue
                elif tool.get("type") == "mcp":
                    continue
                non_mcp_tools.append(tool)
            api_params["tools"] = non_mcp_tools

        # Start API call timing
        model = api_params.get("model", "unknown")
        provider = self.get_provider_name().lower()
        self.start_api_call_timing(model)

        # Wrap LLM API call with tracing for agent attribution
        with trace_llm_api_call(
            agent_id=agent_id or "unknown",
            provider=provider,
            model=model,
            operation="stream",
        ):
            try:
                if "openai" in provider:
                    stream = await client.responses.create(**api_params)
                elif "claude" in provider:
                    if "betas" in api_params:
                        stream = await client.beta.messages.create(**api_params)
                    else:
                        stream = await client.messages.create(**api_params)
                else:
                    # Enable usage tracking in streaming responses (required for token counting)
                    # Chat Completions API (used by Grok, Groq, Together, Fireworks, etc.)
                    if api_params.get("stream"):
                        api_params["stream_options"] = {"include_usage": True}

                    # OpenRouter: Enable cost tracking and web search plugin
                    configure_openrouter_extra_body(api_params, all_params)

                    # Track messages for interrupted stream estimation (multi-agent restart handling)
                    if hasattr(self, "_interrupted_stream_messages"):
                        self._interrupted_stream_messages = processed_messages.copy()
                        self._interrupted_stream_model = all_params.get("model", "gpt-4o")
                        self._stream_usage_received = False

                    stream = await client.chat.completions.create(**api_params)
            except Exception as e:
                self.end_api_call_timing(success=False, error=str(e))
                raise

        async for chunk in self._process_stream(stream, all_params, agent_id):
            yield chunk

    async def _stream_handle_custom_and_mcp_exceptions(
        self,
        error: Exception,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk]:
        """Handle MCP exceptions with fallback streaming."""

        """Handle MCP errors with specific messaging and fallback to non-MCP tools."""
        async with self._stats_lock:
            self._mcp_tool_failures += 1
            call_index_snapshot = self._mcp_tool_calls_count

        if MCPErrorHandler:
            log_type, user_message, _ = MCPErrorHandler.get_error_details(error)
        else:
            log_type, user_message = "mcp_error", "[MCP] Error occurred"

        logger.warning(
            f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}",
        )

        # Yield detailed MCP error status as StreamChunk
        yield StreamChunk(
            type="mcp_status",
            status="mcp_tools_failed",
            content=f"MCP tool call failed (call #{call_index_snapshot}): {user_message}",
            source="mcp_error",
        )

        # Yield user-friendly error message
        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        async for chunk in self._stream_without_custom_and_mcp_tools(
            messages,
            tools,
            client,
            **kwargs,
        ):
            yield chunk

    def _track_mcp_function_names(self, tools: list[dict[str, Any]]) -> None:
        """Track MCP function names for fallback filtering."""
        for tool in tools:
            if tool.get("type") == "function":
                name = tool.get("function", {}).get("name") if "function" in tool else tool.get("name")
                if name:
                    self._mcp_function_names.add(name)

    async def _check_circuit_breaker_before_execution(self) -> bool:
        """Check circuit breaker status before executing MCP functions."""
        if not (self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker and MCPSetupManager and MCPCircuitBreakerManager):
            return True

        # Get current mcp_tools servers using utility functions
        normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
            normalized_servers,
        )

        filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
            mcp_tools_servers,
            self._mcp_tools_circuit_breaker,
        )

        if not filtered_servers:
            logger.warning("All MCP servers blocked by circuit breaker")
            return False

        return True

    async def _record_mcp_circuit_breaker_failure(
        self,
        error: Exception,
        agent_id: str | None = None,
    ) -> None:
        """Record MCP failure for circuit breaker if enabled."""
        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
            try:
                # Get current mcp_tools servers for circuit breaker failure recording
                normalized_servers = MCPSetupManager.normalize_mcp_servers(
                    self.mcp_servers,
                )
                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
                    normalized_servers,
                )

                await MCPCircuitBreakerManager.record_event(
                    mcp_tools_servers,
                    self._mcp_tools_circuit_breaker,
                    "failure",
                    error_message=str(error),
                    backend_name=self.backend_name,
                    agent_id=agent_id,
                )
            except Exception as cb_error:
                logger.warning(f"Failed to record circuit breaker failure: {cb_error}")

    async def _record_mcp_circuit_breaker_success(
        self,
        servers_to_use: list[dict[str, Any]],
    ) -> None:
        """Record MCP success for circuit breaker if enabled."""
        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker and self._mcp_client and MCPCircuitBreakerManager:
            try:
                connected_server_names = self._mcp_client.get_server_names() if hasattr(self._mcp_client, "get_server_names") else []
                if connected_server_names:
                    connected_server_configs = [server for server in servers_to_use if server.get("name") in connected_server_names]
                    if connected_server_configs:
                        await MCPCircuitBreakerManager.record_event(
                            connected_server_configs,
                            self._mcp_tools_circuit_breaker,
                            "success",
                            backend_name=self.backend_name,
                            agent_id=self.agent_id,
                        )
            except Exception as cb_error:
                logger.warning(f"Failed to record circuit breaker success: {cb_error}")

    def _trim_message_history(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Trim message history to prevent unbounded growth."""
        if MCPMessageManager:
            return MCPMessageManager.trim_message_history(
                messages,
                self._max_mcp_message_history,
            )
        return messages

    async def cleanup_mcp(self) -> None:
        """Cleanup MCP connections."""
        await self._cancel_all_background_tool_jobs()
        if self._mcp_client and MCPResourceManager:
            await MCPResourceManager.cleanup_mcp_client(
                self._mcp_client,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )
            self._mcp_client = None
            self._mcp_initialized = False
            self._mcp_functions.clear()
            self._mcp_function_names.clear()

    async def __aenter__(self) -> CustomToolAndMCPBackend:
        """Async context manager entry."""
        # Initialize MCP tools if configured
        if MCPResourceManager:
            await MCPResourceManager.setup_mcp_context_manager(
                self,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Async context manager exit with automatic resource cleanup."""
        if MCPResourceManager:
            await MCPResourceManager.cleanup_mcp_context_manager(
                self,
                logger_instance=logger,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

        await self._cancel_all_background_tool_jobs()

        # Don't suppress the original exception if one occurred
        return False

    def get_mcp_server_count(self) -> int:
        """Get count of stdio/streamable-http servers."""
        if not (self.mcp_servers and MCPSetupManager):
            return 0

        normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
            normalized_servers,
        )
        return len(mcp_tools_servers)

    def yield_mcp_status_chunks(
        self,
        use_mcp: bool,
    ) -> AsyncGenerator[StreamChunk]:
        """Yield MCP status chunks for connection and availability."""

        async def _generator():
            # If MCP is configured but unavailable, inform the user and fall back
            if self.mcp_servers and not use_mcp:
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_unavailable",
                    content="⚠️ [MCP] Setup failed or no tools available; continuing without MCP",
                    source="mcp_setup",
                )

            # Yield MCP connection status if MCP tools are available
            if use_mcp and self.mcp_servers:
                server_count = self.get_mcp_server_count()
                if server_count > 0:
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_connected",
                        content=f"✅ [MCP] Connected to {server_count} servers",
                        source="mcp_setup",
                    )

            if use_mcp:
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tools_initiated",
                    content=f"🔧 [MCP] {len(self._mcp_functions)} tools available",
                    source="mcp_session",
                )

        return _generator()

    def is_mcp_tool_call(self, tool_name: str) -> bool:
        """Check if a tool call is an MCP function.

        Checks both the registered function set and the naming convention.
        The naming convention fallback is important because _mcp_functions
        gets cleared during cleanup, but we may still need to recognize
        MCP tools in the orchestrator's enforcement phase after recovery.
        """
        # Check registered functions first
        if tool_name in self._mcp_functions:
            return True
        # Fallback to naming convention (mcp__<server>__<tool>)
        return tool_name.startswith("mcp__")

    def is_custom_tool_call(self, tool_name: str) -> bool:
        """Check if a tool call is a custom tool function.

        Checks both the registered tool names and the naming convention.
        The naming convention fallback is important because _custom_tool_names
        may not include all custom tools if they were registered dynamically.
        """
        # Check registered tool names first
        if tool_name in self._custom_tool_names:
            return True
        # Fallback to naming convention (custom_tool__<name>)
        return tool_name.startswith("custom_tool__")

    def get_mcp_tools_formatted(self) -> list[dict[str, Any]]:
        """Get MCP tools formatted for specific API format."""
        if not self._mcp_functions:
            return []

        # Determine format based on backend type
        mcp_tools = []
        mcp_tools = self.formatter.format_mcp_tools(self._mcp_functions)

        # Track function names for fallback filtering
        self._track_mcp_function_names(mcp_tools)

        return mcp_tools
