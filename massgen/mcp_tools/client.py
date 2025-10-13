# -*- coding: utf-8 -*-
"""
MCP client implementation for connecting to MCP servers. This module provides enhanced MCP client
functionality to connect with MCP servers and integrate external tools into the MassGen workflow.
"""
import asyncio
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from types import TracebackType
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from mcp import ClientSession, StdioServerParameters
from mcp import types as mcp_types
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..logger_config import logger
from .circuit_breaker import MCPCircuitBreaker
from .config_validator import MCPConfigValidator
from .exceptions import (
    MCPConnectionError,
    MCPError,
    MCPServerError,
    MCPTimeoutError,
    MCPValidationError,
)
from .security import substitute_env_variables, prepare_command, sanitize_tool_name, validate_tool_arguments


class ConnectionState(Enum):
    """Connection state for MCP clients."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"


# Hook types reference: https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-python#hook-types
class HookType(Enum):
    """Available hook types for MCP tool execution."""

    PRE_TOOL_USE = "PreToolUse"


def _ensure_timedelta(value: Union[int, float, timedelta], default_seconds: float) -> timedelta:
    """
    Ensure a value is converted to timedelta for consistent timeout handling.

    Raises:
        MCPValidationError: If value is invalid
    """
    if isinstance(value, timedelta):
        if value.total_seconds() <= 0:
            raise MCPValidationError(
                f"Timeout must be positive, got {value.total_seconds()} seconds",
                field="timeout",
                value=value.total_seconds(),
            )
        return value
    elif isinstance(value, (int, float)):
        if value <= 0:
            raise MCPValidationError(
                f"Timeout must be positive, got {value} seconds",
                field="timeout",
                value=value,
            )
        return timedelta(seconds=value)
    else:
        logger.warning(f"Invalid timeout value {value}, using default {default_seconds}s")
        return timedelta(seconds=default_seconds)


@dataclass
class _ServerClient:
    """Internal container for per-server state."""
    session: Optional[ClientSession] = None
    manager_task: Optional[asyncio.Task] = None
    connected_event: asyncio.Event = None
    disconnect_event: asyncio.Event = None
    connection_lock: asyncio.Lock = None
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    initialized: bool = False

    def __post_init__(self):
        if self.connected_event is None:
            self.connected_event = asyncio.Event()
        if self.disconnect_event is None:
            self.disconnect_event = asyncio.Event()
        if self.connection_lock is None:
            self.connection_lock = asyncio.Lock()


class MCPClient:
    """
    Unified MCP client for communicating with single or multiple MCP servers.
    Provides improved security, error handling, and async context management.
    
    Accepts a list of server configurations and automatically handles:
    - Consistent tool naming: Always uses prefixed names (mcp__server__tool)
    - Circuit breaker protection for all servers
    - Parallel connection for multi-server scenarios
    - Sequential connection for single-server scenarios
    """

    def __init__(
        self,
        server_configs: List[Dict[str, Any]],
        *,
        timeout_seconds: int = 30,
        allowed_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
        hooks: Optional[Dict[HookType, List[Callable[[str, Dict[str, Any]], Awaitable[bool]]]]] = None,
    ):
        """
        Initialize MCP client.

        Args:
            server_configs: List of server configuration dicts (always a list, even for single server)
            timeout_seconds: Timeout for operations in seconds
            allowed_tools: Optional list of tool names to include (if None, includes all)
            exclude_tools: Optional list of tool names to exclude (if None, excludes none)
            status_callback: Optional async callback for status updates
            hooks: Optional dict mapping hook types to lists of hook functions
        """
        # Validate all server configs
        self._server_configs = [MCPConfigValidator.validate_server_config(config) for config in server_configs]
        
        # Set name to first server's name for backward compatibility
        self.name = self._server_configs[0]["name"]
        
        self.timeout_seconds = timeout_seconds
        self.allowed_tools = allowed_tools
        self.exclude_tools = exclude_tools
        self.status_callback = status_callback
        self.hooks = hooks or {}
        
        # Initialize circuit breaker for ALL scenarios
        self._circuit_breaker = MCPCircuitBreaker()
        
        # Per-server tracking
        self._server_clients: Dict[str, _ServerClient] = {}
        for config in self._server_configs:
            self._server_clients[config["name"]] = _ServerClient()
        
        # Unified registry for tools
        self.tools: Dict[str, mcp_types.Tool] = {}
        self._tool_to_server: Dict[str, str] = {}
        
        # Connection management
        self._initialized = False
        self._cleanup_done = False
        self._cleanup_lock = asyncio.Lock()
        self._context_managed = False

    @property
    def session(self) -> Optional[ClientSession]:
        """Return first server's session for backward compatibility."""
        if self._server_configs:
            first_server_name = self._server_configs[0]["name"]
            server_client = self._server_clients.get(first_server_name)
            if server_client:
                return server_client.session
        return None

    def _get_server_session(self, server_name: str) -> ClientSession:
        """Get session for server, raising error if not connected."""
        server_client = self._server_clients.get(server_name)
        if not server_client or not server_client.session:
            raise MCPConnectionError(
                f"Server '{server_name}' not connected",
                server_name=server_name
            )
        return server_client.session

    async def connect(self) -> None:
        """Connect to MCP server(s) and discover capabilities with circuit breaker integration."""
        if self._initialized:
            return
        
        logger.info(f"Connecting to {len(self._server_configs)} MCP server(s)...")
        
        # Send connecting status if callback is available
        if self.status_callback:
            await self.status_callback(
                "connecting",
                {
                    "message": f"Connecting to {len(self._server_configs)} MCP server(s)",
                    "server_count": len(self._server_configs),
                },
            )
        
        if len(self._server_configs) > 1:
            # Multi-server: connect in parallel
            await self._connect_all_parallel()
        else:
            # Single-server: connect sequentially
            await self._connect_single()
        
        # Only mark as initialized if at least one server connected successfully
        self._initialized = any(sc.initialized for sc in self._server_clients.values())
        
        # Count successful and failed connections
        successful_count = len([sc for sc in self._server_clients.values() if sc.initialized])
        failed_count = len(self._server_configs) - successful_count
        
        # Send connection summary status if callback is available
        if self.status_callback:
            await self.status_callback(
                "connection_summary",
                {
                    "message": f"Connected to {successful_count}/{len(self._server_configs)} server(s)" + (f" ({failed_count} failed)" if failed_count > 0 else ""),
                    "successful_count": successful_count,
                    "failed_count": failed_count,
                    "total_count": len(self._server_configs),
                    "tools_count": len(self.tools),
                },
            )

    async def _connect_server(self, server_name: str, config: Dict[str, Any]) -> bool:
        """Connect to a single server with circuit breaker integration.
        
        Returns:
            True on success, False on failure
        """
        server_client = self._server_clients[server_name]
        
        async with server_client.connection_lock:
            # Check circuit breaker
            if self._circuit_breaker.should_skip_server(server_name):
                logger.warning(f"Skipping server {server_name} due to circuit breaker")
                server_client.connection_state = ConnectionState.FAILED
                return False
            
            server_client.connection_state = ConnectionState.CONNECTING
            
            try:
                # Start background manager task
                server_client.manager_task = asyncio.create_task(
                    self._run_manager(server_name, config)
                )
                
                # Wait for connection
                await asyncio.wait_for(server_client.connected_event.wait(), timeout=30.0)
                
                if not server_client.initialized or server_client.connection_state != ConnectionState.CONNECTED:
                    raise MCPConnectionError(f"Failed to connect to {server_name}")
                
                # Record success
                self._circuit_breaker.record_success(server_name)
                logger.info(f"✅ MCP server '{server_name}' connected successfully!")
                return True
                
            except Exception as e:
                self._circuit_breaker.record_failure(server_name)
                server_client.connection_state = ConnectionState.FAILED
                logger.error(f"Failed to connect to {server_name}: {e}")
                
                # Cleanup manager task to prevent resource leak
                if server_client.manager_task and not server_client.manager_task.done():
                    server_client.disconnect_event.set()
                    try:
                        await asyncio.wait_for(server_client.manager_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"Manager task for {server_name} didn't shutdown gracefully, cancelling")
                        server_client.manager_task.cancel()
                        try:
                            await server_client.manager_task
                        except asyncio.CancelledError:
                            pass
                    except Exception as cleanup_error:
                        logger.error(f"Error cleaning up manager task for {server_name}: {cleanup_error}")
                    finally:
                        server_client.manager_task = None
                
                return False

    async def _connect_single(self) -> None:
        """Connect to single server."""
        config = self._server_configs[0]
        server_name = config["name"]
        
        success = await self._connect_server(server_name, config)
        if not success:
            raise MCPConnectionError(f"Failed to connect to {server_name}")

    async def _connect_all_parallel(self) -> None:
        """Connect to all servers in parallel."""
        tasks = [self._connect_server(c["name"], c) for c in self._server_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log results
        successful = sum(1 for r in results if r is True)
        logger.info(f"Connected to {successful}/{len(self._server_configs)} servers")

    def _create_transport_context(self, config: Dict[str, Any]):
        """Create the appropriate transport context manager based on config."""
        transport_type = config.get("type", "stdio")
        server_name = config["name"]

        if transport_type == "stdio":
            command = config.get("command", [])
            args = config.get("args", [])

            logger.debug(f"Setting up stdio transport for {server_name}: command={command}, args={args}")

            # Handle command preparation
            if isinstance(command, str):
                full_command = prepare_command(command)
                if args:
                    full_command.extend(args)
            elif isinstance(command, list):
                full_command = command + (args or [])
            else:
                full_command = args or []

            if not full_command:
                raise MCPConnectionError(f"No command specified for stdio transport in {server_name}")

            # Merge provided env with system env
            env = config.get("env", {})
            if env:
                env = {**get_default_environment(), **env}
            else:
                env = get_default_environment()

            # Perform environment variable substitution for args
            substituted_args = []
            for arg in full_command[1:] if len(full_command) > 1 else []:
                if isinstance(arg, str):
                    try:
                        substituted_args.append(substitute_env_variables(arg))
                    except ValueError as e:
                        raise MCPConnectionError(f"Environment variable substitution failed in args: {e}", server_name=server_name) from e
                else:
                    substituted_args.append(arg)

            # Perform environment variable substitution for env dict
            for key, value in list(env.items()):
                if isinstance(value, str):
                    try:
                        env[key] = substitute_env_variables(value)
                    except ValueError as e:
                        raise MCPConnectionError(f"Environment variable substitution failed for {key}: {e}", server_name=server_name) from e

            # Extract cwd if provided in config
            cwd = config.get("cwd")

            server_params = StdioServerParameters(
                command=full_command[0],
                args=substituted_args,
                env=env,
                cwd=cwd,
            )
            return stdio_client(server_params)

        elif transport_type == "streamable-http":
            url = config["url"]
            headers = config.get("headers", {})

            # Perform environment variable substitution for headers
            substituted_headers = {}
            for key, value in headers.items():
                if isinstance(value, str):
                    try:
                        substituted_headers[key] = substitute_env_variables(value)
                    except ValueError as e:
                        raise MCPConnectionError(f"Environment variable substitution failed in header {key}: {e}", server_name=server_name) from e
                else:
                    substituted_headers[key] = value

            timeout_raw = config.get("timeout", self.timeout_seconds)
            http_read_timeout_raw = config.get("http_read_timeout", 60 * 5)

            timeout = _ensure_timedelta(timeout_raw, self.timeout_seconds)
            http_read_timeout = _ensure_timedelta(http_read_timeout_raw, 60 * 5)

            return streamablehttp_client(
                url=url,
                headers=substituted_headers,
                timeout=timeout,
                sse_read_timeout=http_read_timeout,
            )
        else:
            raise MCPConnectionError(f"Unsupported transport type: {transport_type}")

    async def _run_manager(self, server_name: str, config: Dict[str, Any]) -> None:
        """Background task that owns the transport and session contexts for a server."""
        server_client = self._server_clients[server_name]
        connection_successful = False
        
        try:
            transport_ctx = self._create_transport_context(config)

            async with transport_ctx as session_params:
                read, write = session_params[0:2]

                session_timeout_timedelta = _ensure_timedelta(self.timeout_seconds, 30.0)

                async with ClientSession(read, write, read_timeout_seconds=session_timeout_timedelta) as session:
                    # Initialize and expose session
                    server_client.session = session
                    await session.initialize()
                    await self._discover_capabilities(server_name, config)
                    server_client.initialized = True
                    server_client.connection_state = ConnectionState.CONNECTED
                    connection_successful = True
                    server_client.connected_event.set()

                    logger.info(f"✅ MCP server '{server_name}' connected successfully!")

                    # Send connected status if callback is available
                    if self.status_callback:
                        await self.status_callback(
                            "connected",
                            {
                                "server": server_name,
                                "message": f"Server '{server_name}' ready",
                            },
                        )

                    # Wait until disconnect is requested
                    await server_client.disconnect_event.wait()

        except Exception as e:
            logger.error(f"MCP manager error for {server_name}: {e}", exc_info=True)

            if self.status_callback:
                await self.status_callback(
                    "error",
                    {
                        "server": server_name,
                        "message": f"Failed to connect to MCP server '{server_name}': {e}",
                        "error": str(e),
                    },
                )

            if not server_client.connected_event.is_set():
                server_client.connected_event.set()
        finally:
            # Clear session state
            server_client.initialized = False
            server_client.session = None
            if not connection_successful:
                server_client.connection_state = ConnectionState.FAILED
                if not server_client.connected_event.is_set():
                    server_client.connected_event.set()
            else:
                server_client.connection_state = ConnectionState.DISCONNECTED

    async def _discover_capabilities(self, server_name: str, config: Dict[str, Any]) -> None:
        """Discover server capabilities (tools, resources, prompts) with name prefixing for multi-server."""
        logger.debug(f"Discovering capabilities for {server_name}")
        
        session = self._get_server_session(server_name)

        try:
            # Combine backend-level and per-server tool filtering
            server_exclude = config.get("exclude_tools", [])
            combined_exclude = list(set((self.exclude_tools or []) + server_exclude))
            
            server_allowed = config.get("allowed_tools")
            combined_allowed = server_allowed if server_allowed is not None else self.allowed_tools

            # List tools
            available_tools = await session.list_tools()
            tools_list = getattr(available_tools, "tools", []) if available_tools else []

            for tool in tools_list:
                if combined_exclude and tool.name in combined_exclude:
                    continue
                if combined_allowed is None or tool.name in combined_allowed:
                    # Always apply name prefixing for consistency
                    prefixed_name = sanitize_tool_name(tool.name, server_name)
                    
                    self.tools[prefixed_name] = tool
                    self._tool_to_server[prefixed_name] = server_name

            logger.info(f"Discovered capabilities for {server_name}: "
                       f"{len([t for t, s in self._tool_to_server.items() if s == server_name])} tools")

        except Exception as e:
            logger.error(f"Failed to discover server capabilities for {server_name}: {e}", exc_info=True)
            raise MCPConnectionError(f"Failed to discover server capabilities: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        if not self._initialized:
            return
        
        # Disconnect all servers (works for single or multiple)
        tasks = [
            self._disconnect_one(name, client)
            for name, client in self._server_clients.items()
            if client.connection_state != ConnectionState.DISCONNECTED
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._initialized = False

    async def _disconnect_one(self, server_name: str, server_client: _ServerClient) -> None:
        """Disconnect a single server."""
        server_client.connection_state = ConnectionState.DISCONNECTING

        if server_client.manager_task and not server_client.manager_task.done():
            server_client.disconnect_event.set()
            try:
                await asyncio.wait_for(server_client.manager_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Manager task for {server_name} didn't shutdown gracefully, cancelling")
                server_client.manager_task.cancel()
                try:
                    await server_client.manager_task
                except asyncio.CancelledError:
                    logger.debug(f"Manager task for {server_name} cancelled successfully")
            except Exception as e:
                logger.error(f"Error during manager task shutdown for {server_name}: {e}")
            finally:
                server_client.manager_task = None

        server_client.initialized = False
        server_client.connection_state = ConnectionState.DISCONNECTED

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool with validation and timeout handling.

        Args:
            tool_name: Name of the tool to call (always prefixed as mcp__server__toolname)
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            MCPError: If tool is not available
            MCPConnectionError: If no active session
            MCPValidationError: If arguments are invalid
            MCPTimeoutError: If tool call times out
            MCPServerError: If tool execution fails
        """
        if tool_name not in self.tools:
            available_tools = list(self.tools.keys())
            raise MCPError(
                f"Tool '{tool_name}' not available",
                context={"available_tools": available_tools, "total": len(available_tools)},
            )

        # Validate tool arguments
        try:
            validated_arguments = validate_tool_arguments(arguments)
        except ValueError as e:
            raise MCPValidationError(
                f"Invalid tool arguments: {e}",
                field="arguments",
                value=arguments,
                context={"tool_name": tool_name},
            ) from e

        # Execute pre-tool hooks
        pre_tool_hooks = self.hooks.get(HookType.PRE_TOOL_USE, [])
        for hook in pre_tool_hooks:
            try:
                allowed = await hook(tool_name, validated_arguments)
                if not allowed:
                    raise MCPValidationError(
                        "Tool call blocked by pre-tool hook",
                        field="tool_name",
                        value=tool_name,
                        context={"arguments": validated_arguments},
                    )
            except Exception as e:
                if isinstance(e, MCPValidationError):
                    raise
                logger.warning(f"Pre-tool hook error for {tool_name}: {e}", exc_info=True)

        # Extract server name from prefixed tool name (always prefixed)
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            raise MCPError(f"Tool '{tool_name}' not mapped to any server")
        
        # Extract original tool name (remove prefix - always prefixed)
        original_tool_name = tool_name[len(f"mcp__{server_name}__"):]

        session = self._get_server_session(server_name)

        logger.debug(f"Calling tool {original_tool_name} on {server_name} with arguments: {validated_arguments}")

        # Send tool call start status if callback is available
        if self.status_callback:
            await self.status_callback(
                "tool_call_start",
                {
                    "server": server_name,
                    "tool": original_tool_name,
                    "message": f"Calling tool '{original_tool_name}' on server '{server_name}'",
                    "arguments": validated_arguments,
                },
            )

        try:
            # Add timeout to tool calls
            result = await asyncio.wait_for(
                session.call_tool(original_tool_name, validated_arguments),
                timeout=self.timeout_seconds,
            )
            logger.debug(f"Tool {original_tool_name} completed successfully on {server_name}")

            # Send tool call success status if callback is available
            if self.status_callback:
                await self.status_callback(
                    "tool_call_success",
                    {
                        "server": server_name,
                        "tool": original_tool_name,
                        "message": f"Tool '{original_tool_name}' executed successfully",
                    },
                )

            return result

        except asyncio.TimeoutError:
            if self.status_callback:
                await self.status_callback(
                    "tool_call_timeout",
                    {
                        "server": server_name,
                        "tool": original_tool_name,
                        "message": f"Tool '{original_tool_name}' timed out after {self.timeout_seconds} seconds",
                        "timeout": self.timeout_seconds,
                    },
                )

            # Record failure with circuit breaker
            self._circuit_breaker.record_failure(server_name)

            raise MCPTimeoutError(
                f"Tool call timed out after {self.timeout_seconds} seconds",
                timeout_seconds=self.timeout_seconds,
                operation=f"call_tool({original_tool_name})",
                context={"tool_name": original_tool_name, "server_name": server_name},
            )
        except Exception as e:
            logger.error(f"Tool call failed for {original_tool_name} on {server_name}: {e}", exc_info=True)

            # Record failure with circuit breaker
            self._circuit_breaker.record_failure(server_name)

            if self.status_callback:
                await self.status_callback(
                    "tool_call_error",
                    {
                        "server": server_name,
                        "tool": original_tool_name,
                        "message": f"Tool '{original_tool_name}' failed: {e}",
                        "error": str(e),
                    },
                )

            raise MCPServerError(
                f"Tool call failed: {e}",
                server_name=server_name,
                context={"tool_name": original_tool_name, "arguments": validated_arguments},
            ) from e

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self.tools.keys())

    def is_connected(self) -> bool:
        """Check if any servers are connected."""
        return self._initialized and any(sc.initialized for sc in self._server_clients.values())

    def get_server_names(self) -> List[str]:
        """Get list of connected server names."""
        return [name for name, sc in self._server_clients.items() if sc.initialized]

    def get_active_sessions(self) -> List[ClientSession]:
        """Return active MCP ClientSession objects for all connected servers."""
        sessions = []
        for server_client in self._server_clients.values():
            if server_client.session is not None and server_client.initialized:
                sessions.append(server_client.session)
        return sessions



    async def health_check_all(self) -> Dict[str, bool]:
        """
        Perform health check on all connected MCP servers.

        Returns:
            Dictionary mapping server names to health status
        """
        health_status = {}

        for server_name, server_client in self._server_clients.items():
            if not server_client.initialized or not server_client.session:
                health_status[server_name] = False
                continue

            try:
                await server_client.session.list_tools()
                health_status[server_name] = True
            except Exception as e:
                logger.warning(f"Health check failed for {server_name}: {e}")
                health_status[server_name] = False

        return health_status

    async def health_check(self) -> bool:
        """
        Perform a health check on all servers.

        Returns:
            True if all connected servers are healthy, False otherwise
        """
        health_status = await self.health_check_all()
        return all(health_status.values()) if health_status else False

    async def _reconnect_failed_servers(self, max_retries: int = 3) -> Dict[str, bool]:
        """
        Attempt to reconnect any failed servers with circuit breaker integration.

        Args:
            max_retries: Maximum number of reconnection attempts per server

        Returns:
            Dictionary mapping server names to reconnection success status
        """
        health_status = await self.health_check_all()
        reconnect_results = {}

        for server_name, is_healthy in health_status.items():
            if not is_healthy:
                # Check circuit breaker before reconnecting
                if self._circuit_breaker.should_skip_server(server_name):
                    logger.warning(f"Skipping reconnection for {server_name} due to circuit breaker")
                    reconnect_results[server_name] = False
                    continue

                logger.info(f"Attempting to reconnect failed server: {server_name}")
                
                # Find the config for this server
                config = next((c for c in self._server_configs if c["name"] == server_name), None)
                if not config:
                    reconnect_results[server_name] = False
                    continue

                success = False
                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            await asyncio.sleep(1.0 * (2 ** attempt))  # Exponential backoff

                        # Disconnect first
                        server_client = self._server_clients[server_name]
                        await self._disconnect_one(server_name, server_client)

                        # Reconnect
                        server_client.connected_event = asyncio.Event()
                        server_client.disconnect_event = asyncio.Event()
                        server_client.manager_task = asyncio.create_task(
                            self._run_manager(server_name, config)
                        )
                        await asyncio.wait_for(server_client.connected_event.wait(), timeout=30.0)

                        if server_client.initialized:
                            self._circuit_breaker.record_success(server_name)
                            success = True
                            logger.info(f"Successfully reconnected server: {server_name}")
                            break
                    except Exception as e:
                        logger.warning(f"Reconnection attempt {attempt + 1} failed for {server_name}: {e}")
                        self._circuit_breaker.record_failure(server_name)

                reconnect_results[server_name] = success
            else:
                reconnect_results[server_name] = True

        return reconnect_results

    async def reconnect(self, max_retries: int = 3) -> bool:
        """
        Attempt to reconnect all servers with circuit breaker integration.

        Args:
            max_retries: Maximum number of reconnection attempts
                Uses exponential backoff between retries: 2s, 4s, 8s, 16s...

        Returns:
            True if all reconnections successful, False otherwise
        """
        results = await self._reconnect_failed_servers(max_retries)
        return all(results.values()) if results else False

    async def _cleanup(self) -> None:
        """Comprehensive cleanup of all resources."""
        async with self._cleanup_lock:
            if self._cleanup_done:
                return

            logger.debug(f"Starting cleanup for MCPClient")

            try:
                # Disconnect all servers
                await self.disconnect()

                # Clear all references
                self.tools.clear()
                self._tool_to_server.clear()

                self._cleanup_done = True
                logger.debug(f"Cleanup completed for MCPClient")

            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                raise

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry."""
        self._context_managed = True
        await self.connect()
        return self

    async def __aexit__(
        self,
        _exc_type: Optional[type],
        _exc_val: Optional[BaseException],
        _exc_tb: Optional[TracebackType],
    ) -> None:
        """Async context manager exit."""
        try:
            await self._cleanup()
        except Exception as e:
            logger.error(f"Error during context manager cleanup: {e}")
        finally:
            self._context_managed = False

    @classmethod
    async def create_and_connect(
        cls,
        server_configs: List[Dict[str, Any]],
        *,
        timeout_seconds: int = 30,
        allowed_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ) -> "MCPClient":
        """
        Create and connect MCP client in one step.

        Args:
            server_configs: List of server configuration dictionaries
            timeout_seconds: Timeout for operations in seconds
            allowed_tools: Optional list of tool names to include
            exclude_tools: Optional list of tool names to exclude

        Returns:
            Connected MCPClient instance
        """
        client = cls(
            server_configs,
            timeout_seconds=timeout_seconds,
            allowed_tools=allowed_tools,
            exclude_tools=exclude_tools,
        )
        await client.connect()
        return client