# -*- coding: utf-8 -*-
"""
Base class with MCP (Model Context Protocol) support.
Provides common MCP functionality for backends that support MCP integration.
Inherits from LLMBackend and adds MCP-specific features.
"""
from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import uuid
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
)

import httpx
from pydantic import BaseModel

from ..logger_config import log_backend_activity, logger
from ..nlip.schema import (
    NLIPControlField,
    NLIPFormatField,
    NLIPMessageType,
    NLIPRequest,
    NLIPTokenField,
    NLIPToolCall,
)
from ..tool import ToolManager
from ..utils import CoordinationStage
from .base import LLMBackend, StreamChunk


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


class UploadFileError(Exception):
    """Raised when an upload specified in configuration fails to process."""


class UnsupportedUploadSourceError(UploadFileError):
    """Raised when a provided upload source cannot be processed (e.g., URL without fetch support)."""


class CustomToolChunk(NamedTuple):
    """Streaming chunk from custom tool execution."""

    data: str  # Chunk data to stream to user
    completed: bool  # True for the last chunk only
    accumulated_result: str  # Final accumulated result (only when completed=True)


class ExecutionContext(BaseModel):
    """Execution context for MCP tool execution."""

    messages: List[Dict[str, Any]] = []
    agent_system_message: Optional[str] = None
    agent_id: Optional[str] = None
    backend_name: Optional[str] = None
    current_stage: Optional[CoordinationStage] = None

    # These will be computed after initialization
    system_messages: Optional[List[Dict[str, Any]]] = None
    user_messages: Optional[List[Dict[str, Any]]] = None
    prompt: Optional[List[Dict[str, Any]]] = None

    def __init__(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        agent_system_message: Optional[str] = None,
        agent_id: Optional[str] = None,
        backend_name: Optional[str] = None,
        current_stage: Optional[CoordinationStage] = None,
    ):
        """Initialize execution context."""
        super().__init__(
            messages=messages or [],
            agent_system_message=agent_system_message,
            agent_id=agent_id,
            backend_name=backend_name,
            current_stage=current_stage,
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
                    raise ValueError("Execution Context expects only one system message during PRESENTATION stage")
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

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize backend with MCP support."""
        super().__init__(api_key, **kwargs)

        # Custom tools support - initialize before api_params_handler
        self.custom_tool_manager = ToolManager()
        self._custom_tool_names: set[str] = set()

        # Store execution context for custom tool execution
        self._execution_context = None

        # NLIP routing support (injected by agent configuration)
        self._nlip_router = None
        self._nlip_enabled = False

        # Register custom tools if provided
        custom_tools = kwargs.get("custom_tools", [])
        if custom_tools:
            self._register_custom_tools(custom_tools)

        # MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_function_names: set[str] = set()

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
                logger.warning("MCP tools circuit breaker config not available, disabling circuit breaker functionality")
                self._circuit_breakers_enabled = False
        else:
            if not self.mcp_servers:
                # No MCP servers configured - skip circuit breaker initialization silently
                self._circuit_breakers_enabled = False
            else:
                logger.warning("Circuit breakers not available - proceeding without circuit breaker protection")

        # Function registry for mcp_tools-based servers (stdio + streamable-http)
        self._mcp_functions: Dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)

        # Initialize backend name and agent ID for MCP operations
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get("agent_id", None)

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

    def _backend_call_to_nlip(self, call: Dict[str, Any]) -> Optional[NLIPToolCall]:
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

            # Parse arguments (handle both string and dict)
            args = call.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except json.JSONDecodeError as exc:
                    snippet = args[:200] + "..." if len(args) > 200 else args
                    logger.error(
                        f"[NLIP] Failed to parse arguments for {name}: {exc}. " f"Invalid JSON (truncated): {snippet}",
                    )
                    return None
            elif not isinstance(args, dict):
                logger.error(f"[NLIP] Arguments must be string or dict, got {type(args)}")
                return None

            return NLIPToolCall(
                tool_id=call_id,
                tool_name=name,
                parameters=args,
                require_confirmation=False,
            )
        except Exception as exc:
            logger.error(f"[NLIP] Conversion failed: {exc}")
            return None

    def _build_nlip_request(self, call: Dict[str, Any]) -> NLIPRequest:
        """Construct an NLIP request payload for a backend tool call."""
        if not self._nlip_router:
            raise RuntimeError("NLIP router is not configured")

        # Inject agent_cwd into arguments (same as standard path)
        original_args = call.get("arguments", "{}")
        arguments = json.loads(original_args or "{}") if isinstance(original_args, str) else dict(original_args or {})
        if self.filesystem_manager and self.filesystem_manager.cwd:
            if "agent_cwd" not in arguments or arguments.get("agent_cwd") is None:
                arguments["agent_cwd"] = self.filesystem_manager.cwd
                logger.debug(f"[NLIP] Injected agent_cwd: {self.filesystem_manager.cwd}")

        call_with_cwd = call.copy()
        call_with_cwd["arguments"] = json.dumps(arguments) if isinstance(original_args, str) else arguments

        nlip_call = self._backend_call_to_nlip(call_with_cwd)
        if not nlip_call:
            raise ValueError("Failed to convert call to NLIP format")

        execution_context: Dict[str, Any] = {}
        if getattr(self, "_execution_context", None):
            try:
                execution_context = self._execution_context.model_dump()
            except Exception as exc:
                logger.warning(f"[NLIP] Failed to serialize execution context: {exc}")
        else:
            logger.debug("[NLIP] No execution context available when building NLIP request")

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
    async def _process_stream(self, stream, all_params, agent_id: Optional[str] = None) -> AsyncGenerator[StreamChunk, None]:
        """Process stream."""
        yield StreamChunk(type="error", error="Not implemented")

    # Custom tools support
    def _register_custom_tools(self, custom_tools: List[Dict[str, Any]]) -> None:
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

                    # Normalize function field to list
                    func_field = tool_config.get("function")
                    if isinstance(func_field, str):
                        functions = [func_field]
                    elif isinstance(func_field, list):
                        functions = func_field
                    else:
                        logger.error(
                            f"Invalid function field type: {type(func_field)}. " f"Must be str or List[str].",
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
                            logger.info(f"Injecting agent_cwd for {func}: {self.filesystem_manager.cwd}")
                        elif self.filesystem_manager:
                            logger.warning(f"filesystem_manager exists but cwd is None for {func}")
                        else:
                            logger.warning(f"No filesystem_manager available for {func}")

                        # Load the function first if custom name is needed
                        if names[i] and names[i] != func:
                            # Load function to apply custom name
                            if path:
                                loaded_func = self.custom_tool_manager._load_function_from_path(path, func)
                            else:
                                loaded_func = self.custom_tool_manager._load_builtin_function(func)

                            if loaded_func is None:
                                logger.error(f"Could not load function '{func}' from path: {path}")
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
                        registered_name = names[i] if names[i] else func

                        # Track tool name for categorization
                        if registered_name.startswith("custom_tool__"):
                            self._custom_tool_names.add(registered_name)
                        else:
                            self._custom_tool_names.add(f"custom_tool__{registered_name}")

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
    ) -> Optional[List[Any]]:
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
        tool_request: Dict[str, Any],
    ) -> AsyncGenerator[Tuple[str, bool], None]:
        """Stream execution results from tool manager, yielding (data, is_log) tuples.

        Args:
            tool_request: Tool request dictionary with name and input

        Yields:
            Tuple of (data: str, is_log: bool) for each result block
        """
        try:
            async for result in self.custom_tool_manager.execute_tool(
                tool_request,
                execution_context=self._execution_context.model_dump(),
            ):
                is_log = getattr(result, "is_log", False)

                if hasattr(result, "output_blocks"):
                    for block in result.output_blocks:
                        data = ""
                        if hasattr(block, "data"):
                            data = str(block.data)

                        if data:
                            yield (data, is_log)

        except Exception as e:
            logger.error(f"Error in custom tool execution: {e}")
            yield (f"Error: {str(e)}", True)

    async def stream_custom_tool_execution(
        self,
        call: Dict[str, Any],
    ) -> AsyncGenerator[CustomToolChunk, None]:
        """Stream custom tool execution with differentiation between logs and final results.

        This method:
        - Streams all results (logs and final) to users in real-time
        - Accumulates only is_log=False results for message history
        - Yields CustomToolChunk with completed=False for intermediate results
        - Yields final CustomToolChunk with completed=True and accumulated result

        Args:
            call: Function call dictionary with name and arguments

        Yields:
            CustomToolChunk instances for streaming to user
        """
        import json

        # Parse arguments
        arguments = json.loads(call["arguments"]) if isinstance(call["arguments"], str) else call["arguments"]

        # Ensure agent_cwd is always injected if filesystem_manager is available
        # This provides a fallback in case preset_args didn't work during registration
        if self.filesystem_manager and self.filesystem_manager.cwd:
            if "agent_cwd" not in arguments or arguments.get("agent_cwd") is None:
                arguments["agent_cwd"] = self.filesystem_manager.cwd
                logger.info(f"Dynamically injected agent_cwd at execution time: {self.filesystem_manager.cwd}")

        tool_request = {
            "name": call["name"],
            "input": arguments,
        }

        accumulated_result = ""

        # Stream all results and accumulate only is_log=True
        async for data, is_log in self._stream_execution_results(tool_request):
            # Yield streaming chunk to user
            yield CustomToolChunk(
                data=data,
                completed=False,
                accumulated_result="",
            )

            # Accumulate only final results for message history
            if not is_log:
                accumulated_result += data

        # Yield final chunk with accumulated result
        yield CustomToolChunk(
            data="",
            completed=True,
            accumulated_result=accumulated_result or "Tool executed successfully",
        )

    def _get_custom_tools_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-formatted schemas for all registered custom tools."""
        return self.custom_tool_manager.fetch_tool_schemas()

    def _categorize_tool_calls(
        self,
        captured_calls: List[Dict[str, Any]],
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """Categorize tool calls into MCP, custom, and provider categories.

        Args:
            captured_calls: List of tool call dictionaries with name and arguments

        Returns:
            Tuple of (mcp_calls, custom_calls, provider_calls)

        Note:
            Provider calls include workflow tools (new_answer, vote) that must NOT
            be executed by backends.
        """
        mcp_calls: List[Dict] = []
        custom_calls: List[Dict] = []
        provider_calls: List[Dict] = []

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

    @abstractmethod
    def _append_tool_result_message(
        self,
        updated_messages: List[Dict[str, Any]],
        call: Dict[str, Any],
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
        updated_messages: List[Dict[str, Any]],
        call: Dict[str, Any],
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

    async def _execute_tool_with_logging(
        self,
        call: Dict[str, Any],
        config: ToolExecutionConfig,
        updated_messages: List[Dict[str, Any]],
        processed_call_ids: Set[str],
    ) -> AsyncGenerator[StreamChunk, None]:
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

        if tool_name in ["new_answer", "vote"]:
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
            # Yield tool called status
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_called,
                content=f"{config.emoji_prefix} Calling {tool_name}...",
                source=f"{config.source_prefix}{tool_name}",
            )

            # Yield arguments chunk
            arguments_str = call.get("arguments", "{}")
            yield StreamChunk(
                type=config.chunk_type,
                status="function_call",
                content=f"Arguments for Calling {tool_name}: {arguments_str}",
                source=f"{config.source_prefix}{tool_name}",
            )

            # Execute tool via callback
            result = None
            result_str = ""
            result_obj = None

            if config.tool_type == "custom":
                # Check if execution_callback returns an async generator (streaming)
                callback_result = config.execution_callback(call)

                # Handle async generator (streaming custom tools)
                if hasattr(callback_result, "__aiter__"):
                    # This is an async generator - stream intermediate results
                    async for chunk in callback_result:
                        # Yield intermediate chunks if available
                        if hasattr(chunk, "data") and chunk.data and not chunk.completed:
                            # Stream intermediate output to user
                            yield StreamChunk(
                                type=config.chunk_type,
                                status="custom_tool_output",
                                content=chunk.data,
                                source=f"{config.source_prefix}{tool_name}",
                            )
                        elif hasattr(chunk, "completed") and chunk.completed:
                            # Extract final accumulated result
                            result_str = chunk.accumulated_result
                    result = result_str
                else:
                    # Handle regular await (non-streaming custom tools)
                    result = await callback_result
                    result_str = str(result)
            else:  # MCP
                result_str, result_obj = await config.execution_callback(call["name"], call["arguments"])
                result = result_str

            # Check for MCP failure after retries
            if config.tool_type == "mcp" and result_str.startswith("Error:"):
                logger.warning(f"MCP tool {tool_name} failed after retries: {result_str}")
                error_msg = result_str
                self._append_tool_error_message(updated_messages, call, error_msg, config.tool_type)
                processed_call_ids.add(call.get("call_id", ""))
                yield StreamChunk(
                    type=config.chunk_type,
                    status=config.status_error,
                    content=f"{config.error_emoji} {error_msg}",
                    source=f"{config.source_prefix}{tool_name}",
                )
                return

            # Append result to messages
            self._append_tool_result_message(updated_messages, call, result, config.tool_type)

            # Yield results chunk
            # For MCP tools, try to extract text from result_obj if available
            display_result = result_str
            if config.tool_type == "mcp" and result_obj:
                try:
                    if hasattr(result_obj, "content") and isinstance(result_obj.content, list):
                        if len(result_obj.content) > 0 and hasattr(result_obj.content[0], "text"):
                            display_result = result_obj.content[0].text
                except (AttributeError, IndexError, TypeError):
                    pass  # Fall back to result_str

            yield StreamChunk(
                type=config.chunk_type,
                status="function_call_output",
                content=f"Results for Calling {tool_name}: {display_result}",
                source=f"{config.source_prefix}{tool_name}",
            )

            # Yield completion status
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_response,
                content=f"{config.success_emoji} {tool_name} completed",
                source=f"{config.source_prefix}{tool_name}",
            )

            processed_call_ids.add(call.get("call_id", ""))
            logger.info(f"Executed {config.tool_type} tool: {tool_name}")

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
            )

            # Yield error status chunk
            yield StreamChunk(
                type=config.chunk_type,
                status=config.status_error,
                content=f"{config.error_emoji} {error_msg}",
                source=f"{config.source_prefix}{tool_name}",
            )

            # Append error to messages
            self._append_tool_error_message(updated_messages, call, error_msg, config.tool_type)

            processed_call_ids.add(call.get("call_id", ""))

    async def _stream_tool_execution_via_nlip(
        self,
        call: Dict[str, Any],
        config: ToolExecutionConfig,
        updated_messages: List[Dict[str, Any]],
        processed_call_ids: Set[str],
    ) -> AsyncGenerator[StreamChunk, None]:
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
        )

        yield StreamChunk(
            type=config.chunk_type,
            status="function_call",
            content=f"Arguments for Calling {tool_name}: {arguments_str}",
            source=f"{config.source_prefix}{tool_name}",
        )

        request = self._build_nlip_request(call)

        async for response in self._nlip_router.route_message(request):
            chunk = self._convert_nlip_stream_chunk(response.content, config, tool_name)
            if chunk:
                yield chunk
                continue

            if response.tool_results:
                matching_result = self._select_matching_tool_result(response.tool_results, call_id)
                if not matching_result:
                    continue

                if matching_result.status == "error":
                    error_msg = matching_result.error or "Unknown error"
                    self._append_tool_error_message(updated_messages, call, error_msg, config.tool_type)
                    processed_call_ids.add(call_id)
                    yield StreamChunk(
                        type=config.chunk_type,
                        status=config.status_error,
                        content=f"{config.error_emoji} {tool_name}: {error_msg}",
                        source=f"{config.source_prefix}{tool_name}",
                    )
                    return

                result_text = self._extract_nlip_result_text(matching_result, config.tool_type)
                self._append_tool_result_message(updated_messages, call, result_text, config.tool_type)
                processed_call_ids.add(call_id)

                yield StreamChunk(
                    type=config.chunk_type,
                    status="function_call_output",
                    content=f"Results for Calling {tool_name}: {result_text}",
                    source=f"{config.source_prefix}{tool_name}",
                )

                yield StreamChunk(
                    type=config.chunk_type,
                    status=config.status_response,
                    content=f"{config.success_emoji} {tool_name} completed",
                    source=f"{config.source_prefix}{tool_name}",
                )
                return

        raise Exception("NLIP router returned no result")

    def _convert_nlip_stream_chunk(
        self,
        content: Optional[Dict[str, Any]],
        config: ToolExecutionConfig,
        tool_name: str,
    ) -> Optional[StreamChunk]:
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
                logger.warning(f"[NLIP] Large stream chunk ({len(content_str)} chars) for {tool_name}")
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
        tool_results: List[Any],
        call_id: str,
    ) -> Optional[Any]:
        """Return the NLIPToolResult that matches the requested call_id."""
        if not tool_results:
            logger.error("[NLIP] No tool results available for selection")
            return None

        if not call_id:
            logger.warning("[NLIP] No call_id provided for tool result selection; defaulting to first result")
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
            logger.debug(f"[NLIP] Extracted string result for {tool_name} ({len(raw_result)} chars)")
            return raw_result

        if isinstance(raw_result, dict) and "output" in raw_result:
            output = str(raw_result["output"])
            logger.debug(
                f"[NLIP] Extracted dict['output'] result for {tool_name} ({len(output)} chars)",
            )
            return output

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
    def _extract_text_from_content(content: Any) -> Optional[str]:
        """Extract text from MCP-style content payload."""
        if not content:
            return None

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
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
                return CustomToolAndMCPBackend._extract_text_from_content(content["content"])

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
                    logger.warning("All MCP servers blocked by circuit breaker during setup")
                    return
                if len(filtered_servers) < len(mcp_tools_servers):
                    logger.info(f"Circuit breaker filtered {len(mcp_tools_servers) - len(filtered_servers)} servers during setup")
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
                logger.warning("MCP client setup failed, falling back to no-MCP streaming")
                return

            # Convert tools to functions using consolidated utility
            self._mcp_functions.update(
                MCPResourceManager.convert_tools_to_functions(
                    self._mcp_client,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                    hook_manager=getattr(self, "function_hook_manager", None),
                ),
            )
            self._mcp_initialized = True
            logger.info(f"Successfully initialized MCP sessions with {len(self._mcp_functions)} tools converted to functions")

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
    ) -> Tuple[str, Any]:
        """Execute MCP function with exponential backoff retry logic."""
        # Check if this specific MCP tool is blocked by planning mode
        if self.is_mcp_tool_blocked(function_name):
            logger.info(f"[MCP] Planning mode enabled - blocking MCP tool: {function_name}")
            error_str = f"🚫 [MCP] Tool '{function_name}' blocked during coordination (planning mode active)"
            return error_str, {"error": error_str, "blocked_by": "planning_mode", "function_name": function_name}

        # Convert JSON string to dict for shared utility
        try:
            args = json.loads(arguments_json) if isinstance(arguments_json, str) else arguments_json
        except (json.JSONDecodeError, ValueError) as e:
            error_str = f"Error: Invalid JSON arguments: {e}"
            return error_str, {"error": error_str}

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
            return "Error: MCPExecutionManager unavailable", {"error": "MCPExecutionManager unavailable"}

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
        return str(result), result

    async def _process_upload_files(
        self,
        messages: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
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
        extra_content: List[Dict[str, Any]] = []
        has_file_search_files = False

        for entry in upload_entries:
            if not isinstance(entry, dict):
                logger.warning("upload_files entry is not a dict: %s", entry)
                raise UploadFileError("Each upload_files entry must be a mapping")

            # Check for file_path (File Search documents/code)
            file_path_value = entry.get("file_path")
            if file_path_value:
                # Process file_path entry for File Search
                file_content = self._process_file_path_entry(file_path_value, all_params)
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
        all_params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
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

    def _resolve_local_path(self, raw_path: str, all_params: Dict[str, Any]) -> Path:
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

    def _read_base64(self, path: Path) -> Tuple[str, str]:
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
        all_params: Dict[str, Any],
    ) -> Tuple[str, str]:
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

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""

        agent_id = kwargs.get("agent_id", None)

        # Build execution context for tools (generic, not tool-specific)
        self._execution_context = ExecutionContext(
            messages=messages,
            agent_system_message=kwargs.get("system_message", None),
            agent_id=self.agent_id,
            backend_name=self.backend_name,
            current_stage=self.coordination_stage,
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
                        async for chunk in self._stream_with_custom_and_mcp_tools(current_messages, tools, client, **kwargs):
                            yield chunk

                    else:
                        # NON-MCP MODE: Simple passthrough streaming
                        logger.info("Using no-MCP mode")

                        # Start non-MCP streaming
                        async for chunk in self._stream_without_custom_and_mcp_tools(messages, tools, client, **kwargs):
                            yield chunk

                except Exception as e:
                    # Enhanced error handling for MCP-related errors during streaming
                    if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                        # Record failure for circuit breaker
                        await self._record_mcp_circuit_breaker_failure(e, agent_id)

                        # Handle MCP exceptions with fallback
                        async for chunk in self._stream_handle_custom_and_mcp_exceptions(e, messages, tools, client, **kwargs):
                            yield chunk
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

                if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                    # Handle MCP exceptions with fallback
                    async for chunk in self._stream_handle_custom_and_mcp_exceptions(e, messages, tools, client, **kwargs):
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
                    async for chunk in self._stream_without_custom_and_mcp_tools(messages, tools, client, **kwargs):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                await self._cleanup_client(client)

    @abstractmethod
    async def _stream_with_custom_and_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        yield StreamChunk(type="error", error="Not implemented")

    @abstractmethod
    def _create_client(self, **kwargs):
        pass

    async def _stream_without_custom_and_mcp_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Simple passthrough streaming without MCP processing."""

        agent_id = kwargs.get("agent_id", None)
        all_params = {**self.config, **kwargs}
        processed_messages = await self._process_upload_files(messages, all_params)
        api_params = await self.api_params_handler.build_api_params(processed_messages, tools, all_params)

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

        if "openai" in self.get_provider_name().lower():
            stream = await client.responses.create(**api_params)
        elif "claude" in self.get_provider_name().lower():
            if "betas" in api_params:
                stream = await client.beta.messages.create(**api_params)
            else:
                stream = await client.messages.create(**api_params)
        else:
            stream = await client.chat.completions.create(**api_params)

        async for chunk in self._process_stream(stream, all_params, agent_id):
            yield chunk

    async def _stream_handle_custom_and_mcp_exceptions(
        self,
        error: Exception,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP exceptions with fallback streaming."""

        """Handle MCP errors with specific messaging and fallback to non-MCP tools."""
        async with self._stats_lock:
            self._mcp_tool_failures += 1
            call_index_snapshot = self._mcp_tool_calls_count

        if MCPErrorHandler:
            log_type, user_message, _ = MCPErrorHandler.get_error_details(error)
        else:
            log_type, user_message = "mcp_error", "[MCP] Error occurred"

        logger.warning(f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}")

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

        async for chunk in self._stream_without_custom_and_mcp_tools(messages, tools, client, **kwargs):
            yield chunk

    def _track_mcp_function_names(self, tools: List[Dict[str, Any]]) -> None:
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
        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)

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
        agent_id: Optional[str] = None,
    ) -> None:
        """Record MCP failure for circuit breaker if enabled."""
        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
            try:
                # Get current mcp_tools servers for circuit breaker failure recording
                normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)

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

    async def _record_mcp_circuit_breaker_success(self, servers_to_use: List[Dict[str, Any]]) -> None:
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

    def _trim_message_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trim message history to prevent unbounded growth."""
        if MCPMessageManager:
            return MCPMessageManager.trim_message_history(messages, self._max_mcp_message_history)
        return messages

    async def cleanup_mcp(self) -> None:
        """Cleanup MCP connections."""
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

    async def __aenter__(self) -> "CustomToolAndMCPBackend":
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
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Async context manager exit with automatic resource cleanup."""
        if MCPResourceManager:
            await MCPResourceManager.cleanup_mcp_context_manager(
                self,
                logger_instance=logger,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )
        # Don't suppress the original exception if one occurred
        return False

    def get_mcp_server_count(self) -> int:
        """Get count of stdio/streamable-http servers."""
        if not (self.mcp_servers and MCPSetupManager):
            return 0

        normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)
        return len(mcp_tools_servers)

    def yield_mcp_status_chunks(self, use_mcp: bool) -> AsyncGenerator[StreamChunk, None]:
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
        """Check if a tool call is an MCP function."""
        return tool_name in self._mcp_functions

    def is_custom_tool_call(self, tool_name: str) -> bool:
        """Check if a tool call is a custom tool function."""
        return tool_name in self._custom_tool_names

    def get_mcp_tools_formatted(self) -> List[Dict[str, Any]]:
        """Get MCP tools formatted for specific API format."""
        if not self._mcp_functions:
            return []

        # Determine format based on backend type
        mcp_tools = []
        mcp_tools = self.formatter.format_mcp_tools(self._mcp_functions)

        # Track function names for fallback filtering
        self._track_mcp_function_names(mcp_tools)

        return mcp_tools
