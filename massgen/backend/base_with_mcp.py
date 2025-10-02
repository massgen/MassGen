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

from ..logger_config import log_backend_activity, logger
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
        MultiMCPClient,
    )
except ImportError as e:
    logger.warning(f"MCP import failed: {e}")
    # Create fallback assignments for all MCP imports
    MultiMCPClient = None
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


class MCPBackend(LLMBackend):
    """Base backend class with MCP (Model Context Protocol) support."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize backend with MCP support."""
        super().__init__(api_key, **kwargs)

        # MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_function_names: set[str] = set()

        # Circuit breaker for MCP tools (stdio + streamable-http)
        self._mcp_tools_circuit_breaker = None
        self._circuit_breakers_enabled = MCPCircuitBreaker is not None

        # Initialize circuit breaker if available
        if self._circuit_breakers_enabled:
            # Use shared utility to build circuit breaker configuration
            mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools") if MCPConfigHelper else None

            if mcp_tools_config:
                self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
                logger.info("Circuit breaker initialized for MCP tools")
            else:
                logger.warning("MCP tools circuit breaker config not available, disabling circuit breaker functionality")
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
                timeout_seconds=30,
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

        Supports two forms:
        - {"image_path": "..."}: loads file, encodes to base64, injects image entry
        - {"url": "..."}: injects image entry referencing remote URL

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

        for entry in upload_entries:
            if not isinstance(entry, dict):
                logger.warning("upload_files entry is not a dict: %s", entry)
                raise UploadFileError("Each upload_files entry must be a mapping")

            path_value = entry.get("image_path")
            url_value = entry.get("url")

            if path_value:
                resolved = Path(path_value).expanduser()
                if not resolved.is_absolute():
                    cwd = self.config.get("cwd")
                    if cwd:
                        resolved = Path(cwd).joinpath(resolved)
                    else:
                        resolved = resolved.resolve()

                if not resolved.exists():
                    raise UploadFileError(f"File not found: {resolved}")

                mime_type, _ = mimetypes.guess_type(resolved.as_posix())
                if not mime_type:
                    mime_type = "application/octet-stream"

                try:
                    data = resolved.read_bytes()
                except OSError as exc:
                    raise UploadFileError(f"Failed to read file {resolved}: {exc}") from exc

                encoded = base64.b64encode(data).decode("utf-8")
                extra_content.append(
                    {
                        "type": "image",
                        "base64": encoded,
                        "mime_type": mime_type,
                        "source_path": str(resolved),
                    },
                )
                continue

            if url_value:
                extra_content.append({"type": "image", "url": url_value})
                continue

            raise UploadFileError(
                "upload_files entry must specify either 'image_path' or 'url'",
            )

        if not extra_content:
            return processed_messages

        if processed_messages:
            last_message = processed_messages[-1].copy()
            last_content = list(last_message.get("content", []))
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

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""

        agent_id = kwargs.get("agent_id", None)

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

                    if use_mcp:
                        # MCP MODE: Recursive function call detection and execution
                        logger.info("Using recursive MCP execution mode")

                        current_messages = self._trim_message_history(messages.copy())

                        # Start recursive MCP streaming
                        async for chunk in self._stream_with_mcp_tools(current_messages, tools, client, **kwargs):
                            yield chunk

                    else:
                        # NON-MCP MODE: Simple passthrough streaming
                        logger.info("Using no-MCP mode")

                        # Start non-MCP streaming
                        async for chunk in self._stream_without_mcp_tools(messages, tools, client, **kwargs):
                            yield chunk

                except Exception as e:
                    # Enhanced error handling for MCP-related errors during streaming
                    if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                        # Record failure for circuit breaker
                        await self._record_mcp_circuit_breaker_failure(e, agent_id)

                        # Handle MCP exceptions with fallback
                        async for chunk in self._stream_handle_mcp_exceptions(e, messages, tools, client, **kwargs):
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
                    async for chunk in self._stream_handle_mcp_exceptions(e, messages, tools, client, **kwargs):
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
                    async for chunk in self._stream_without_mcp_tools(messages, tools, client, **kwargs):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                await self._cleanup_client(client)

    async def _stream_without_mcp_tools(
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

    async def _stream_handle_mcp_exceptions(
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

        async for chunk in self._stream_without_mcp_tools(messages, tools, client, **kwargs):
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

                await MCPCircuitBreakerManager.record_failure(
                    mcp_tools_servers,
                    self._mcp_tools_circuit_breaker,
                    str(error),
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
                        await MCPCircuitBreakerManager.record_success(
                            connected_server_configs,
                            self._mcp_tools_circuit_breaker,
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

    async def __aenter__(self) -> "MCPBackend":
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
