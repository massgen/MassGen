# -*- coding: utf-8 -*-
"""
Lightweight MCP manager for Gemini that wraps backend_utils with Gemini-specific streaming status, session conversion, and planning-mode checks.
"""

import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from ..logger_config import log_backend_activity, logger
from ..mcp_tools import (
    MCPCircuitBreakerManager,
    MCPClient,
    MCPConfigurationError,
    MCPConfigValidator,
    MCPConnectionError,
    MCPError,
    MCPErrorHandler,
    MCPExecutionManager,
    MCPResourceManager,
    MCPRetryHandler,
    MCPServerError,
    MCPSetupManager,
    MCPTimeoutError,
    MCPValidationError,
)
from ..mcp_tools.hooks import convert_sessions_to_permission_sessions
from .base import StreamChunk


class GeminiMCPManager:
    def __init__(self, backend_instance) -> None:
        self.backend = backend_instance
        # References to backend state/config
        self.mcp_servers = getattr(self.backend, "mcp_servers", [])
        self.allowed_tools = getattr(self.backend, "allowed_tools", None)
        self.exclude_tools = getattr(self.backend, "exclude_tools", None)
        self.agent_id = getattr(self.backend, "agent_id", None)

        # Counters (will be updated on backend instance)
        self._mcp_tool_calls_count = getattr(self.backend, "_mcp_tool_calls_count", 0)
        self._mcp_tool_failures = getattr(self.backend, "_mcp_tool_failures", 0)
        self._mcp_tool_successes = getattr(self.backend, "_mcp_tool_successes", 0)

        # MCP client and init state mirror backend
        self._mcp_client: Optional[MCPClient] = getattr(self.backend, "_mcp_client", None)
        self._mcp_initialized: bool = getattr(self.backend, "_mcp_initialized", False)

        # Circuit breaker and filesystem manager references
        self._mcp_tools_circuit_breaker = getattr(self.backend, "_mcp_tools_circuit_breaker", None)
        self.filesystem_manager = getattr(self.backend, "filesystem_manager", None)

    async def setup_mcp_with_status_stream(self, agent_id: Optional[str] = None) -> AsyncGenerator[StreamChunk, None]:
        """Initialize MCP client with status streaming."""
        if not self.mcp_servers or self._mcp_initialized:
            if False:
                yield  # make this an async generator
            return

        status_queue: asyncio.Queue[StreamChunk] = asyncio.Queue()
        _agent_id = agent_id or self.agent_id

        async def status_callback(status: str, details: Dict[str, Any]) -> None:
            """Callback to queue status updates as StreamChunks."""
            chunk = StreamChunk(
                type="mcp_status",
                status=status,
                content=details.get("message", ""),
                source="mcp_tools",
            )
            await status_queue.put(chunk)

        setup_task = asyncio.create_task(self.setup_mcp_internal(_agent_id, status_callback))

        while not setup_task.done():
            try:
                chunk = await asyncio.wait_for(status_queue.get(), timeout=0.1)
                yield chunk
            except asyncio.TimeoutError:
                continue

        try:
            await setup_task
        except Exception as e:
            yield StreamChunk(
                type="mcp_status",
                status="error",
                content=f"MCP setup failed: {e}",
                source="mcp_tools",
            )

    async def setup_mcp_tools(self, agent_id: Optional[str] = None) -> None:
        """Initialize MCP client (sessions only) - wrapper that consumes status stream."""
        async for _ in self.setup_mcp_with_status_stream(agent_id):
            pass

    async def setup_mcp_internal(
        self,
        agent_id: Optional[str] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        """Internal MCP setup logic leveraging backend_utils managers."""
        if not self.mcp_servers or self._mcp_initialized:
            return

        _agent_id = agent_id or self.agent_id

        try:
            # Validate MCP configuration
            backend_config = {
                "mcp_servers": self.mcp_servers,
                "allowed_tools": self.allowed_tools,
                "exclude_tools": self.exclude_tools,
            }

            try:
                validated_config = MCPConfigValidator.validate_backend_mcp_config(backend_config)
                self.mcp_servers = validated_config.get("mcp_servers", self.mcp_servers)
                if status_callback:
                    await status_callback("info", {"message": f"MCP configuration validated: {len(self.mcp_servers)} servers"})
                log_backend_activity("gemini", "MCP configuration validated", {"server_count": len(self.mcp_servers)}, agent_id=_agent_id)
            except MCPConfigurationError as e:
                if status_callback:
                    await status_callback("error", {"message": f"Invalid MCP configuration: {e}"})
                raise RuntimeError(f"Invalid MCP configuration: {e}") from e
            except MCPValidationError as e:
                if status_callback:
                    await status_callback("error", {"message": f"MCP validation error: {e}"})
                raise RuntimeError(f"MCP validation error: {e}") from e
            except Exception as e:
                # Validation unavailable or unexpected error; continue with normalization path
                log_backend_activity("gemini", "MCP validation unavailable or error", {"error": str(e)}, agent_id=_agent_id)

            # Normalize servers
            normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers, backend_name="gemini", agent_id=_agent_id)
            if status_callback:
                await status_callback("info", {"message": f"Setting up MCP sessions for {len(normalized_servers)} servers"})

            # Apply circuit breaker filtering
            if self._mcp_tools_circuit_breaker:
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    normalized_servers,
                    self._mcp_tools_circuit_breaker,
                    backend_name="gemini",
                    agent_id=_agent_id,
                )
            else:
                filtered_servers = normalized_servers

            if not filtered_servers:
                log_backend_activity("gemini", "All MCP servers blocked by circuit breaker", {}, agent_id=_agent_id)
                if status_callback:
                    await status_callback("warning", {"message": "All MCP servers blocked by circuit breaker"})
                return

            # Extract tool filtering parameters
            allowed_tools = backend_config.get("allowed_tools")
            exclude_tools = backend_config.get("exclude_tools")

            # Setup MCP client via resource manager (handles retries and filtering)
            client = await MCPResourceManager.setup_mcp_client(
                servers=filtered_servers,
                allowed_tools=allowed_tools,
                exclude_tools=exclude_tools,
                circuit_breaker=self._mcp_tools_circuit_breaker,
                timeout_seconds=30,
                backend_name="gemini",
                agent_id=_agent_id,
            )

            if not client:
                # Treat as connection failure
                self._mcp_client = None
                self.backend._mcp_client = None
                if status_callback:
                    await status_callback("error", {"message": "MCP connection failed: no servers connected"})
                log_backend_activity("gemini", "MCP connection failed: no servers connected", {}, agent_id=_agent_id)
                return

            # Assign on success
            self._mcp_client = client
            self.backend._mcp_client = client
            self._mcp_initialized = True
            self.backend._mcp_initialized = True

            log_backend_activity("gemini", "MCP sessions initialized successfully", {}, agent_id=_agent_id)
            if status_callback:
                # Attempt to list connected servers
                try:
                    names = client.get_server_names()
                except Exception:
                    names = []
                await status_callback(
                    "success",
                    {"message": f"MCP sessions initialized successfully with {len(names)} servers"},
                )

        except Exception as e:
            # Enhanced error mapping using backend_utils
            log_type, user_message, _ = MCPErrorHandler.get_error_details(e)
            log_backend_activity("gemini", f"MCP {log_type} during setup", {"error": str(e)}, agent_id=_agent_id)
            self._mcp_client = None
            self.backend._mcp_client = None
            self._mcp_initialized = False
            self.backend._mcp_initialized = False
            if status_callback:
                await status_callback("error", {"message": f"MCP session setup failed: {e}"})

    async def handle_mcp_retry_error(self, error: Exception, retry_count: int, max_retries: int) -> Tuple[bool, AsyncGenerator[StreamChunk, None]]:
        """Delegate retry error handling to backend_utils with StreamChunk emission."""
        return await MCPRetryHandler.handle_retry_error(
            error=error,
            retry_count=retry_count,
            max_retries=max_retries,
            stream_chunk_class=StreamChunk,
            backend_name="gemini",
            agent_id=self.agent_id,
        )

    async def handle_mcp_error_and_fallback(self, error: Exception) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with specific messaging and fallback behavior."""
        # increment backend failure counter
        try:
            self.backend._mcp_tool_failures += 1
        except Exception:
            pass

        async for chunk in MCPRetryHandler.handle_error_and_fallback(
            error=error,
            tool_call_count=getattr(self.backend, "_mcp_tool_calls_count", 0),
            stream_chunk_class=StreamChunk,
            backend_name="gemini",
            agent_id=self.agent_id,
        ):
            yield chunk

    async def execute_mcp_function_with_retry(self, function_name: str, args: Dict[str, Any], functions: Dict, agent_id: Optional[str] = None) -> Any:
        """Execute MCP function with retry and circuit breaker recording."""
        _agent_id = agent_id or self.agent_id

        async def stats_callback(action: str) -> int:
            if action == "increment_calls":
                self.backend._mcp_tool_calls_count += 1
                return self.backend._mcp_tool_calls_count
            elif action == "increment_failures":
                self.backend._mcp_tool_failures += 1
                return self.backend._mcp_tool_failures
            return 0

        async def circuit_breaker_callback(event: str, error_msg: str) -> None:
            try:
                if event == "failure":
                    # Record failure for all configured servers
                    servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers, backend_name="gemini", agent_id=_agent_id)
                    if self._mcp_tools_circuit_breaker:
                        await MCPCircuitBreakerManager.record_event(
                            servers,
                            self._mcp_tools_circuit_breaker,
                            "failure",
                            error_message=error_msg,
                            backend_name="gemini",
                            agent_id=_agent_id,
                        )
                else:
                    # Record success only for connected servers
                    connected_names: List[str] = []
                    try:
                        if self._mcp_client:
                            connected_names = self._mcp_client.get_server_names()
                    except Exception:
                        connected_names = []

                    if connected_names and self._mcp_tools_circuit_breaker:
                        servers_to_record = [{"name": name} for name in connected_names]
                        await MCPCircuitBreakerManager.record_event(
                            servers_to_record,
                            self._mcp_tools_circuit_breaker,
                            "success",
                            backend_name="gemini",
                            agent_id=_agent_id,
                        )
            except Exception:
                # Never fail the call due to circuit breaker recording issues
                pass

        return await MCPExecutionManager.execute_function_with_retry(
            function_name=function_name,
            args=args,
            functions=functions,
            max_retries=3,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger,
        )

    async def setup_mcp_sessions_with_retry(self, agent_id: Optional[str] = None, max_retries: int = 5) -> Tuple[bool, AsyncGenerator[StreamChunk, None]]:
        """Attempt to setup sessions with retries; returns (connected, status_chunks)."""
        _agent_id = agent_id or self.agent_id
        chunks: List[StreamChunk] = []
        success: bool = False

        for retry_count in range(1, max_retries + 1):
            # Emit retry status
            chunks.append(
                StreamChunk(
                    type="mcp_status",
                    status="mcp_retry",
                    content=f"Retrying MCP connection (attempt {retry_count}/{max_retries})",
                    source="mcp_tools",
                ),
            )

            try:
                # Apply circuit breaker filtering before attempts
                normalized = MCPSetupManager.normalize_mcp_servers(self.mcp_servers, backend_name="gemini", agent_id=_agent_id)
                if self._mcp_tools_circuit_breaker:
                    filtered = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                        normalized,
                        self._mcp_tools_circuit_breaker,
                        backend_name="gemini",
                        agent_id=_agent_id,
                    )
                else:
                    filtered = normalized

                if not filtered:
                    chunks.append(
                        StreamChunk(
                            type="mcp_status",
                            status="mcp_blocked",
                            content="All MCP servers blocked by circuit breaker",
                            source="mcp_tools",
                        ),
                    )
                    success = False
                    break

                # Validate config for allowed/excluded tools
                try:
                    MCPConfigValidator.validate_backend_mcp_config({"mcp_servers": filtered})
                except Exception:
                    pass

                allowed_items = self.allowed_tools
                exclude_items = self.exclude_tools
                allowed_count = len(allowed_items) if isinstance(allowed_items, (list, tuple, set)) else (1 if allowed_items else 0)
                exclude_count = len(exclude_items) if isinstance(exclude_items, (list, tuple, set)) else (1 if exclude_items else 0)
                logger.debug(
                    "[GeminiMCPManager] Retry filter settings | allowed=%d excluded=%d",
                    allowed_count,
                    exclude_count,
                )

                client = await MCPResourceManager.setup_mcp_client(
                    servers=filtered,
                    allowed_tools=self.allowed_tools,
                    exclude_tools=self.exclude_tools,
                    circuit_breaker=self._mcp_tools_circuit_breaker,
                    timeout_seconds=30,
                    backend_name="gemini",
                    agent_id=_agent_id,
                )

                if client:
                    # Assign to backend/manager and mark success
                    self._mcp_client = client
                    self.backend._mcp_client = client
                    self._mcp_initialized = True
                    self.backend._mcp_initialized = True

                    # Record success event
                    if self._mcp_tools_circuit_breaker:
                        await MCPCircuitBreakerManager.record_event(
                            filtered,
                            self._mcp_tools_circuit_breaker,
                            "success",
                            backend_name="gemini",
                            agent_id=_agent_id,
                        )

                    chunks.append(
                        StreamChunk(
                            type="mcp_status",
                            status="mcp_connected",
                            content=f"MCP connection successful on attempt {retry_count}",
                            source="mcp_tools",
                        ),
                    )
                    success = True
                    break

                # Client not connected; handle as transient error with retry logic
                should_continue, error_chunks = await self.handle_mcp_retry_error(RuntimeError("No servers connected"), retry_count, max_retries)
                # Drain any error chunks into list
                async for ch in error_chunks:
                    chunks.append(ch)
                if not should_continue:
                    success = False
                    break

            except (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError, Exception) as e:
                should_continue, error_chunks = await self.handle_mcp_retry_error(e, retry_count, max_retries)
                async for ch in error_chunks:
                    chunks.append(ch)
                if not should_continue:
                    success = False
                    break

            # Progressive backoff between retries
            await asyncio.sleep(0.5 * retry_count)

        async def _generator():
            for ch in chunks:
                yield ch

        return success, _generator()

    def get_active_mcp_sessions(self, convert_to_permission_sessions: bool = True) -> List[Any]:
        """Return active MCP ClientSession objects, optionally wrapped with permission sessions."""
        sessions: List[Any] = []
        try:
            if self._mcp_client:
                sessions = self._mcp_client.get_active_sessions()
        except Exception:
            sessions = []

        if convert_to_permission_sessions and sessions and self.filesystem_manager:
            try:
                return convert_sessions_to_permission_sessions(sessions, self.filesystem_manager.path_permission_manager)
            except Exception as e:
                logger.error(f"[GeminiMCPManager] Failed to convert sessions to permission sessions: {e}")
                return sessions
        return sessions

    def should_block_mcp_tools_in_planning_mode(self, is_planning_mode: bool, available_tools: List[str]) -> bool:
        """Return True to block MCP tools if planning mode is enabled; logs details."""
        if is_planning_mode:
            log_backend_activity(
                "gemini",
                "MCP tools blocked in planning mode",
                {"blocked_tools": len(available_tools or []), "tools_preview": (available_tools or [])[:5]},
                agent_id=self.agent_id,
            )
            return True
        return False

    async def cleanup_genai_resources(self, stream, client) -> None:
        """Cleanup google-genai resources to avoid unclosed aiohttp sessions."""
        # Close stream
        try:
            if stream is not None:
                close_fn = getattr(stream, "aclose", None) or getattr(stream, "close", None)
                if close_fn is not None:
                    maybe = close_fn()
                    if hasattr(maybe, "__await__"):
                        await maybe
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Stream cleanup failed",
                {"error": str(e)},
                agent_id=self.agent_id,
            )
        # Close internal aiohttp session held by google-genai BaseApiClient
        try:
            if client is not None:
                base_client = getattr(client, "_api_client", None)
                if base_client is not None:
                    session = getattr(base_client, "_aiohttp_session", None)
                    if session is not None and hasattr(session, "close"):
                        if not session.closed:
                            await session.close()
                            log_backend_activity(
                                "gemini",
                                "Closed google-genai aiohttp session",
                                {},
                                agent_id=self.agent_id,
                            )
                        base_client._aiohttp_session = None
                        # Yield control to allow connector cleanup
                        await asyncio.sleep(0)
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Failed to close google-genai aiohttp session",
                {"error": str(e)},
                agent_id=self.agent_id,
            )
        # Close internal async transport if exposed
        try:
            if client is not None and hasattr(client, "aio") and client.aio is not None:
                aio_obj = client.aio
                for method_name in ("close", "stop"):
                    method = getattr(aio_obj, method_name, None)
                    if method:
                        maybe = method()
                        if hasattr(maybe, "__await__"):
                            await maybe
                        break
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Client AIO cleanup failed",
                {"error": str(e)},
                agent_id=self.agent_id,
            )

        # Close client
        try:
            if client is not None:
                for method_name in ("aclose", "close"):
                    method = getattr(client, method_name, None)
                    if method:
                        maybe = method()
                        if hasattr(maybe, "__await__"):
                            await maybe
                        break
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Client cleanup failed",
                {"error": str(e)},
                agent_id=self.agent_id,
            )

    def is_mcp_connected(self) -> bool:
        try:
            return bool(self._mcp_initialized and self._mcp_client and self._mcp_client.is_connected())
        except Exception:
            return False

    def get_mcp_server_names(self) -> List[str]:
        try:
            if self._mcp_client:
                return self._mcp_client.get_server_names()
        except Exception:
            pass
        return []

    def get_mcp_tools(self) -> Dict[str, Any]:
        try:
            if self._mcp_client and hasattr(self._mcp_client, "tools"):
                return self._mcp_client.tools
        except Exception:
            pass
        return {}