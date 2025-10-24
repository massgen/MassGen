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
from abc import abstractmethod
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from ..logger_config import log_backend_activity, logger
from ..tool import ToolManager
from .base import LLMBackend, StreamChunk


class UploadFileError(Exception):
    """Raised when an upload specified in configuration fails to process."""


class UnsupportedUploadSourceError(UploadFileError):
    """Raised when a provided upload source cannot be processed (e.g., URL without fetch support)."""


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

        # Store current messages for execution context
        self._current_messages: Optional[List[Dict[str, Any]]] = None

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

    def supports_upload_files(self) -> bool:
        """Return True if the backend supports `upload_files` preprocessing."""
        return False

    @abstractmethod
    async def _process_stream(self, stream, all_params, agent_id: Optional[str] = None) -> AsyncGenerator[StreamChunk, None]:
        """Process stream."""

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
                        # Load the function first if custom name is needed
                        if names[i] and names[i] != func:
                            # Need to load function and apply custom name
                            if path:
                                loaded_func = self.custom_tool_manager._load_function_from_path(path, func)
                            else:
                                loaded_func = self.custom_tool_manager._load_builtin_function(func)

                            if loaded_func is None:
                                logger.error(f"Could not load function '{func}' from path: {path}")
                                continue

                            # Apply custom name by modifying __name__ attribute
                            loaded_func.__name__ = names[i]

                            # Register with loaded function (no path needed)
                            self.custom_tool_manager.add_tool_function(
                                path=None,
                                func=loaded_func,
                                category=category,
                                preset_args=preset_args_list[i],
                                description=descriptions[i],
                            )
                        else:
                            # No custom name or same as function name, use normal registration
                            self.custom_tool_manager.add_tool_function(
                                path=path,
                                func=func,
                                category=category,
                                preset_args=preset_args_list[i],
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

    async def _execute_custom_tool(self, call: Dict[str, Any]) -> str:
        """Execute a custom tool and return the result.

        Args:
            call: Function call dictionary with name and arguments

        Returns:
            The execution result as a string
        """
        import json

        tool_request = {
            "name": call["name"],
            "input": json.loads(call["arguments"]) if isinstance(call["arguments"], str) else call["arguments"],
        }

        # Build execution context for tools (generic, not tool-specific)
        execution_context = {}

        if self._current_messages:
            # Provide full messages list
            execution_context["messages"] = self._current_messages

            # Extract commonly used fields for convenience
            execution_context["system_message"] = next(
                (msg["content"] for msg in self._current_messages if msg.get("role") == "system"),
                None,
            )
            execution_context["user_message"] = next(
                (msg["content"] for msg in self._current_messages if msg.get("role") == "user"),
                None,
            )

        # Add other useful context information
        if hasattr(self, "agent_id") and self.agent_id:
            execution_context["agent_id"] = self.agent_id
        if hasattr(self, "backend_name") and self.backend_name:
            execution_context["backend_name"] = self.backend_name

        result_text = ""
        try:
            # Pass execution context to ToolManager
            async for result in self.custom_tool_manager.execute_tool(
                tool_request,
                execution_context=execution_context,
            ):
                # Accumulate results
                if hasattr(result, "output_blocks"):
                    for block in result.output_blocks:
                        if hasattr(block, "data"):
                            result_text += str(block.data)
                        elif hasattr(block, "content"):
                            result_text += str(block.content)
                elif hasattr(result, "content"):
                    result_text += str(result.content)
                else:
                    result_text += str(result)
        except Exception as e:
            logger.error(f"Error in custom tool execution: {e}")
            result_text = f"Error: {str(e)}"

        return result_text or "Tool executed successfully"

    def _get_custom_tools_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-formatted schemas for all registered custom tools."""
        return self.custom_tool_manager.fetch_tool_schemas()

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
        # Check if planning mode is enabled - block MCP tool execution during planning
        if self.is_planning_mode_enabled():
            logger.info(f"[MCP] Planning mode enabled - blocking MCP tool execution: {function_name}")
            error_str = "🚫 [MCP] Planning mode active - MCP tools blocked during coordination"
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

        # Store current messages for execution context (for custom tools)
        self._current_messages = messages.copy() if messages else None

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
