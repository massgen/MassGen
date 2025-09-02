"""
MCP client implementation for connecting to MCP servers. This module provides enhanced MCP client functionality to connect with MCP servers and integrate external tools and resources into the MassGen workflow.
"""
import asyncio
from ..logger_config import logger
from datetime import timedelta
from enum import Enum
from types import TracebackType
from typing import Dict, List, Any, Optional, Union


from .exceptions import (
    MCPError, MCPConnectionError, MCPServerError,
    MCPValidationError, MCPTimeoutError
)
from .security import (
    sanitize_tool_name, prepare_command,
    validate_tool_arguments
)
from .config_validator import MCPConfigValidator
from .circuit_breaker import MCPCircuitBreaker
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp import types as mcp_types


class ConnectionState(Enum):
    """Connection state for MCP clients."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"





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
                value=value.total_seconds()
            )
        return value
    elif isinstance(value, (int, float)):
        if value <= 0:
            raise MCPValidationError(
                f"Timeout must be positive, got {value} seconds",
                field="timeout",
                value=value
            )
        return timedelta(seconds=value)
    else:
        logger.warning(f"Invalid timeout value {value}, using default {default_seconds}s")
        return timedelta(seconds=default_seconds)


def _ensure_timeout_seconds(value: Union[int, float, timedelta], default_seconds: float) -> float:
    """
    Ensure a value is converted to seconds for APIs that expect numeric timeouts.

    Returns:
        Timeout in seconds as float
    """
    td = _ensure_timedelta(value, default_seconds)
    return td.total_seconds()


class MCPClient:
    """
    Enhanced MCP client for communicating with MCP servers.
    Provides improved security, error handling, and async context management.
    """

    def __init__(
        self,
        server_config: Dict[str, Any],
        *,
        timeout_seconds: int = 30,
        allowed_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ):
        """
        Initialize MCP client.

        Args:
            server_config: Server configuration dict with keys:
                - name: Server name
                - type: Transport type ("stdio", "streamable-http")
                - command: Command to run (for stdio)
                - url: Server URL (for streamable-http)
                - args: Additional command arguments (for stdio)
                - headers: HTTP headers (for streamable-http)
            timeout_seconds: Timeout for operations in seconds
            allowed_tools: Optional list of tool names to include (if None, includes all)
            exclude_tools: Optional list of tool names to exclude (if None, excludes none)
        """
        # Validate and sanitize configuration
        self.config = MCPConfigValidator.validate_server_config(server_config)
        self.name = self.config["name"]
        self.timeout_seconds = timeout_seconds
        self.allowed_tools = allowed_tools
        self.exclude_tools = exclude_tools
        self.use_official_library = True
        self.tools: Dict[str, mcp_types.Tool] = {}
        self.resources: Dict[str, mcp_types.Resource] = {}
        self.prompts: Dict[str, mcp_types.Prompt] = {}

        # Connection management
        self.session: Optional[ClientSession] = None
        self._initialized = False
        self._connection_state = ConnectionState.DISCONNECTED

        # Background manager for owning transport/session contexts
        self._manager_task: Optional[asyncio.Task] = None
        self._connected_event: asyncio.Event = asyncio.Event()
        self._disconnect_event: asyncio.Event = asyncio.Event()
        self._connection_lock: asyncio.Lock = asyncio.Lock()

        # Resource cleanup tracking
        self._cleanup_done = False
        self._cleanup_lock = asyncio.Lock()

        # Track if we're in an async context manager
        self._context_managed = False

    async def connect(self) -> None:
        """Connect to MCP server and discover capabilities using a background manager task.

        Ensures transport contexts are entered and exited within the same task to satisfy anyio CancelScope requirements.
        """
        async with self._connection_lock:
            
            current_state = self._connection_state

            if current_state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
                logger.debug(f"Client {self.name} already connected or connecting (state: {current_state})")
                return

            if current_state == ConnectionState.DISCONNECTING:
                # Wait for disconnection to complete with timeout
                for _ in range(50):  
                    await asyncio.sleep(0.1)
                    if self._connection_state == ConnectionState.DISCONNECTED:
                        break
                else:
                    raise MCPConnectionError(
                        f"Timeout waiting for disconnection to complete: {self.name}",
                        server_name=self.name,
                        timeout_seconds=5.0
                    )

            if self._connection_state != ConnectionState.DISCONNECTED:
                raise MCPConnectionError(
                    f"Invalid state for connection: {self._connection_state}",
                    server_name=self.name
                )

            logger.info(f"Connecting to MCP server: {self.name}")
            self._connection_state = ConnectionState.CONNECTING

            # Reset events for a new connection attempt
            self._connected_event = asyncio.Event()
            self._disconnect_event = asyncio.Event()

            # Start background manager task
            self._manager_task = asyncio.create_task(self._run_manager())

            # Wait until manager signals readiness (or failure) with timeout
            try:
                await asyncio.wait_for(self._connected_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                await self.disconnect()
                raise MCPConnectionError(
                    f"Connection timeout after 30 seconds for MCP server {self.name}",
                    server_name=self.name,
                    timeout_seconds=30.0
                )

            if not self.session or not self._initialized or self._connection_state != ConnectionState.CONNECTED:
                # Background task failed early
                err: Optional[BaseException] = None
                if self._manager_task:
                    try:
                        await self._manager_task
                    except Exception as e:
                        err = e
                self._connection_state = ConnectionState.FAILED
                await self.disconnect()
                raise MCPConnectionError(
                    f"Failed to connect to MCP server {self.name}: {err or 'unknown error'}",
                    server_name=self.name
                )



    def _create_transport_context(self):
        """Create the appropriate transport context manager based on config."""
        transport_type = self.config.get("type", "stdio")

        if transport_type == "stdio":
            command = self.config.get("command", [])
            args = self.config.get("args", [])

            logger.debug(f"Setting up stdio transport for {self.name}: command={command}, args={args}")

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
                raise MCPConnectionError(f"No command specified for stdio transport in {self.name}")

            logger.debug(f"Full command for {self.name}: {full_command}")

            # Merge provided env with system env
            env = self.config.get("env", {})
            if env:
                env = {**get_default_environment(), **env}
            else:
                env = get_default_environment()
            
            # Perform environment variable substitution
            import re
            import os
            for key, value in env.items():
                if isinstance(value, str) and '${' in value:
                    # Simple environment variable substitution for patterns like ${VAR_NAME}
                    def replace_env_var(match):
                        var_name = match.group(1)
                        return os.environ.get(var_name, match.group(0))  # Return original if not found
                    
                    env[key] = re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}', replace_env_var, value)

            server_params = StdioServerParameters(
                command=full_command[0],
                args=full_command[1:] if len(full_command) > 1 else [],
                env=env
            )
            logger.debug(f"Created StdioServerParameters for {self.name}: {server_params.command} {server_params.args}")
            return stdio_client(server_params)

        elif transport_type == "streamable-http":
            url = self.config["url"]
            headers = self.config.get("headers", {})

            # Use consistent timeout handling
            timeout_raw = self.config.get("timeout", self.timeout_seconds)
            http_read_timeout_raw = self.config.get("http_read_timeout", 60 * 5)

            timeout = _ensure_timedelta(timeout_raw, self.timeout_seconds)
            http_read_timeout = _ensure_timedelta(http_read_timeout_raw, 60 * 5)

            logger.debug(f"Setting up streamable-http transport for {self.name}: url={url}")

            return streamablehttp_client(
                url=url,
                headers=headers,
                timeout=timeout,
                sse_read_timeout=http_read_timeout
            )
        else:
            raise MCPConnectionError(f"Unsupported transport type: {transport_type}")

    async def _run_manager(self) -> None:
        """Background task that owns the transport and session contexts."""
        connection_successful = False
        try:
            transport_ctx = self._create_transport_context()

            async with transport_ctx as session_params:
                read, write = session_params[0:2]

                # Ensure timeout is a timedelta for ClientSession
                session_timeout_timedelta = _ensure_timedelta(self.timeout_seconds, 30.0)

                async with ClientSession(
                    read, write,
                    read_timeout_seconds=session_timeout_timedelta
                ) as session:
                    # Initialize and expose session
                    self.session = session
                    await self.session.initialize()
                    await self._discover_capabilities()
                    self._initialized = True
                    self._connection_state = ConnectionState.CONNECTED
                    connection_successful = True
                    self._connected_event.set()

                    # Add prominent connection success message
                    logger.info(f"✅ MCP server '{self.name}' connected successfully!")
                    print(f"✅ MCP server '{self.name}' connected successfully!")
                    
                    # Wait until disconnect is requested
                    await self._disconnect_event.wait()

        except Exception as e:
            logger.error(f"MCP manager error for {self.name}: {e}", exc_info=True)
            if not self._connected_event.is_set():
                self._connected_event.set()
        finally:
            # Clear session state regardless of success/failure
            self._initialized = False
            self.session = None
            if not connection_successful:
                self._connection_state = ConnectionState.FAILED
                # Only set event if connection failed and event not already set
                if not self._connected_event.is_set():
                    self._connected_event.set()
            else:
                self._connection_state = ConnectionState.DISCONNECTED

    async def disconnect(self) -> None:
        """Disconnect from MCP server. Signals the background manager task to exit so that
        async contexts are closed in the same task where they were opened.
        """
        if self._connection_state == ConnectionState.DISCONNECTED:
            return

        self._connection_state = ConnectionState.DISCONNECTING

        if self._manager_task and not self._manager_task.done():
            self._disconnect_event.set()
            try:
                # Wait for graceful shutdown with timeout
                await asyncio.wait_for(self._manager_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Manager task for {self.name} didn't shutdown gracefully, cancelling")
                self._manager_task.cancel()
                try:
                    await self._manager_task
                except asyncio.CancelledError:
                    logger.debug(f"Manager task for {self.name} cancelled successfully")
            except Exception as e:
                logger.error(f"Error during manager task shutdown for {self.name}: {e}")
            finally:
                self._manager_task = None
                # Reset events for potential future connections
                self._connected_event = asyncio.Event()
                self._disconnect_event = asyncio.Event()

        self._initialized = False
        self._connection_state = ConnectionState.DISCONNECTED

    async def _cleanup(self) -> None:
        """Comprehensive cleanup of all resources."""
        async with self._cleanup_lock:
            if self._cleanup_done:
                return

            logger.debug(f"Starting cleanup for MCPClient {self.name}")

            try:
                # First disconnect gracefully
                await self.disconnect()

                # Clear all references
                self.tools.clear()
                self.resources.clear()
                self.prompts.clear()
                self.allowed_tools = None

                
                self._cleanup_done = True
                logger.debug(f"Cleanup completed for MCPClient {self.name}")

            except Exception as e:
                logger.error(f"Error during cleanup for {self.name}: {e}")
                raise

    async def _discover_capabilities(self) -> None:
        """Discover server capabilities (tools, resources, prompts)."""
        logger.debug(f"Discovering capabilities for {self.name}")

        try:
            if self.session:
                await self._discover_capabilities_official()

                tools_count = len(self.tools)
                resources_count = len(self.resources)
                prompts_count = len(self.prompts)

                logger.info(
                    f"Discovered capabilities for {self.name}: "
                    f"{tools_count} tools, {resources_count} resources, {prompts_count} prompts"
                )
            else:
                logger.warning(f"No session available for capability discovery: {self.name}")

        except Exception as e:
            logger.error(f"Failed to discover server capabilities for {self.name}: {e}", exc_info=True)
            raise MCPConnectionError(f"Failed to discover server capabilities: {e}") from e

    async def _discover_capabilities_official(self) -> None:
        """Discover capabilities using official MCP library."""
        if not self.session:
            raise MCPConnectionError("No active session")

        
        try:
            available_tools = await self.session.list_tools()

            # Filter tools based on include/exclude lists
            for tool in available_tools.tools:
                if self.exclude_tools and tool.name in self.exclude_tools:
                    continue
                if self.allowed_tools is None or tool.name in self.allowed_tools:
                    # Use the official MCP Tool type directly
                    self.tools[tool.name] = tool
        except Exception as e:
            logger.warning(f"Failed to list tools for {self.name}: {e}")

        # List resources (optional)
        try:
            available_resources = await self.session.list_resources()
            for resource in available_resources.resources:
                # Validate resource before storing
                if not hasattr(resource, 'uri') or not resource.uri:
                    logger.warning(f"Invalid resource without URI from server {self.name}")
                    continue
                self.resources[resource.uri] = resource
            logger.debug(f"Discovered {len(self.resources)} resources for {self.name}")
        except (MCPConnectionError, MCPTimeoutError):
            raise
        except Exception as e:
            # Categorize error types for better handling
            error_msg = str(e).lower()
            if any(phrase in error_msg for phrase in ["not supported", "not implemented", "method not found", "unknown method"]):
                logger.debug(f"Resources not supported by server {self.name} (Error: {e})")
            elif "permission" in error_msg or "unauthorized" in error_msg:
                logger.warning(f"Permission denied for resources on server {self.name}: {e}")
            else:
                # Preserve original error context
                logger.error(f"Unexpected error listing resources for {self.name}: {e}", exc_info=True)
                
        try:
            available_prompts = await self.session.list_prompts()
            for prompt in available_prompts.prompts:
                # Validate prompt before storing
                if not hasattr(prompt, 'name') or not prompt.name:
                    logger.warning(f"Invalid prompt without name from server {self.name}")
                    continue
                self.prompts[prompt.name] = prompt
            logger.debug(f"Discovered {len(self.prompts)} prompts for {self.name}")
        except (MCPConnectionError, MCPTimeoutError):
            raise
        except Exception as e:
            # Categorize error types for better handling
            error_msg = str(e).lower()
            if any(phrase in error_msg for phrase in ["not supported", "not implemented", "method not found", "unknown method"]):
                logger.debug(f"Prompts not supported by server {self.name} (Error: {e})")
            elif "permission" in error_msg or "unauthorized" in error_msg:
                logger.warning(f"Permission denied for prompts on server {self.name}: {e}")
            else:
                # Preserve original error context
                logger.error(f"Unexpected error listing prompts for {self.name}: {e}", exc_info=True)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool with validation and timeout handling.

        Args:
            tool_name: Name of the tool to call
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
                f"Tool '{tool_name}' not available on server '{self.name}'",
                context={"available_tools": available_tools, "server_name": self.name}
            )

        if not self.session:
            raise MCPConnectionError(
                "No active session",
                server_name=self.name,
                context={"tool_name": tool_name}
            )

        # Validate tool arguments
        try:
            validated_arguments = validate_tool_arguments(arguments)
        except ValueError as e:
            raise MCPValidationError(
                f"Invalid tool arguments: {e}",
                field="arguments",
                value=arguments,
                context={"tool_name": tool_name, "server_name": self.name}
            ) from e

        logger.debug(f"Calling tool {tool_name} on {self.name} with arguments: {validated_arguments}")

        try:
            # Add timeout to tool calls
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, validated_arguments),
                timeout=self.timeout_seconds
            )
            logger.debug(f"Tool {tool_name} completed successfully on {self.name}")
            return result

        except asyncio.TimeoutError:
            raise MCPTimeoutError(
                f"Tool call timed out after {self.timeout_seconds} seconds",
                timeout_seconds=self.timeout_seconds,
                operation=f"call_tool({tool_name})",
                context={"tool_name": tool_name, "server_name": self.name}
            )
        except Exception as e:
            logger.error(f"Tool call failed for {tool_name} on {self.name}: {e}", exc_info=True)
            raise MCPServerError(
                f"Tool call failed: {e}",
                server_name=self.name,
                context={"tool_name": tool_name, "arguments": validated_arguments}
            ) from e

    async def get_resource(self, uri: str) -> Any:
        """
        Get resource content by URI.

        Args:
            uri: Resource URI

        Returns:
            Resource content
        """
        if not self.session:
            raise MCPConnectionError("No active session")

        try:
            result = await self.session.read_resource(uri)
            return result
        except Exception as e:
            raise MCPServerError(f"Resource read failed: {e}")

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """
        Get prompt template.

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            Prompt content
        """
        if not self.session:
            raise MCPConnectionError("No active session")

        try:
            result = await self.session.get_prompt(name, arguments)
            return result
        except Exception as e:
            raise MCPServerError(f"Prompt get failed: {e}")

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self.tools.keys())

    def get_available_resources(self) -> List[str]:
        """Get list of available resource URIs."""
        return list(self.resources.keys())

    def get_available_prompts(self) -> List[str]:
        """Get list of available prompt names."""
        return list(self.prompts.keys())

    def is_connected(self) -> bool:
        """Check if client is connected to server."""
        return self._initialized and self.session is not None

    async def health_check(self) -> bool:
        """
        Perform a health check on the MCP connection.

        Returns:
            True if connection is healthy, False otherwise
        """
        if not self.is_connected():
            logger.warning(f"Health check failed: {self.name} not connected")
            return False

        try:
            # Try to list tools as a basic health check
            if self.session:
                await self.session.list_tools()
                logger.debug(f"Health check passed for {self.name}")
                return True
        except Exception as e:
            logger.warning(f"Health check failed for {self.name}: {e}")
            return False

        return False

    async def reconnect(self, max_retries: int = 3, retry_delay: float = 1.0) -> bool:
        """
        Attempt to reconnect to the MCP server with retries.

        Args:
            max_retries: Maximum number of reconnection attempts
            retry_delay: Delay between retry attempts in seconds

        Returns:
            True if reconnection successful, False otherwise
        """
        logger.info(f"Attempting to reconnect to {self.name} (max_retries={max_retries})")

        for attempt in range(max_retries):
            try:
                # Disconnect first if connected
                if self.is_connected():
                    await self.disconnect()

                # Wait before retry (except first attempt)
                if attempt > 0:
                    await asyncio.sleep(retry_delay)

                # Attempt reconnection
                await self.connect()

                # Verify connection with health check
                if await self.health_check():
                    logger.info(f"Successfully reconnected to {self.name} on attempt {attempt + 1}")
                    return True
                else:
                    logger.warning(f"Reconnection attempt {attempt + 1} failed health check for {self.name}")

            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed for {self.name}: {e}")

        logger.error(f"Failed to reconnect to {self.name} after {max_retries} attempts")
        return False

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
            logger.error(f"Error during context manager cleanup for {self.name}: {e}")
        finally:
            self._context_managed = False


class MultiMCPClient:
    """
    Multi-MCP client for managing multiple MCP servers simultaneously.

    This class provides a unified interface for working with multiple MCP servers,
    handling connection management, tool discovery, and execution across all servers.
    """

    def __init__(
        self,
        server_configs: List[Dict[str, Any]],
        *,
        timeout_seconds: int = 30,
        allowed_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ):
        """
        Initialize MultiMCP client.

        Args:
            server_configs: List of server configuration dictionaries
            timeout_seconds: Timeout for operations in seconds
            allowed_tools: Optional list of tool names to include (if None, includes all)
            exclude_tools: Optional list of tool names to exclude (if None, excludes none)
        """
        self.server_configs = [MCPConfigValidator.validate_server_config(config) for config in server_configs]
        
        self.timeout_seconds = timeout_seconds
        self.allowed_tools = allowed_tools
        self.exclude_tools = exclude_tools

        # Client management
        self.clients: Dict[str, MCPClient] = {}
        self.tools: Dict[str, mcp_types.Tool] = {}  # Unified tool registry using official types
        self.resources: Dict[str, mcp_types.Resource] = {}  # Unified resource registry using official types
        self.prompts: Dict[str, mcp_types.Prompt] = {}  # Unified prompt registry using official types
        self._tool_to_client: Dict[str, str] = {}  # Tool name -> server name mapping

        # Connection management
        self._initialized = False
        self._connection_lock = asyncio.Lock()
        self._disconnect_lock = asyncio.Lock()
        self._cleanup_done = False

        # Circuit breaker for failing servers
        self._circuit_breaker = MCPCircuitBreaker()

    async def connect(self) -> None:
        """Connect to all MCP servers and discover capabilities."""
        async with self._connection_lock:
            if self._initialized:
                return

            logger.info(f"🔄 Setting up MCP sessions with {len(self.server_configs)} servers...")
            print(f"🔄 Setting up MCP sessions with {len(self.server_configs)} servers...")
            
            await self._connect_all()

    async def _connect_all(self) -> None:
        """Connect to all configured MCP servers in parallel."""
        if self._initialized:
            return

        # Create connection tasks for parallel execution
        async def _connect_single_server(server_config: Dict[str, Any]) -> tuple[str, Optional[MCPClient]]:
            """Connect to a single server and return (server_name, client) or (server_name, None) on failure."""
            server_name = server_config["name"]

            # Check circuit breaker
            if self._circuit_breaker.should_skip_server(server_name):
                logger.warning(f"Skipping server {server_name} due to circuit breaker (too many recent failures)")
                return server_name, None

            try:
                # Create client for this server
                client = MCPClient(
                    server_config,
                    timeout_seconds=self.timeout_seconds,
                    allowed_tools=self.allowed_tools,
                    exclude_tools=self.exclude_tools,
                )

                # Connect the client (this will start its background manager)
                await client.connect()
                logger.info(f"Successfully connected to MCP server: {server_name}")

                # Reset failure count on successful connection
                self._circuit_breaker.record_success(server_name)

                return server_name, client
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_name}: {e}")
                self._circuit_breaker.record_failure(server_name)
                return server_name, None

        # Execute all connections in parallel
        connection_tasks = [_connect_single_server(config) for config in self.server_configs]
        connection_results = await asyncio.gather(*connection_tasks, return_exceptions=True)

        connected_clients = {}
        for result in connection_results:
            if isinstance(result, Exception):
                logger.error(f"Connection task failed with exception: {result}")
                continue

            server_name, client = result
            if client is not None:
                connected_clients[server_name] = client

                # Register tools with server prefix
                for tool_name, tool in client.tools.items():
                    prefixed_name = sanitize_tool_name(tool_name, server_name)

                    # Check for tool name collisions
                    if prefixed_name in self.tools:
                        existing_server = self._tool_to_client.get(prefixed_name, "unknown")
                        logger.warning(
                            f"Tool name collision: '{prefixed_name}' already exists from server '{existing_server}'. "
                            f"Overwriting with tool from server '{server_name}'"
                        )

                    self.tools[prefixed_name] = tool
                    self._tool_to_client[prefixed_name] = server_name

                # Register resources
                for uri, resource in client.resources.items():
                    self.resources[uri] = resource

                # Register prompts with server prefix (consistent with tool naming)
                for prompt_name, prompt in client.prompts.items():
                    # Use consistent naming pattern: mcp__server__prompt
                    prefixed_name = f"mcp__{server_name}__{prompt_name}"

                    # Check for prompt name collisions
                    if prefixed_name in self.prompts:
                        logger.warning(
                            f"Prompt name collision: '{prefixed_name}' already exists. "
                            f"Overwriting with prompt from server '{server_name}'"
                        )

                    self.prompts[prefixed_name] = prompt

                logger.info(f"Registered server '{server_name}' with {len(client.tools)} tools, "
                           f"{len(client.resources)} resources, {len(client.prompts)} prompts")

        # Only set clients dict after all connections are attempted
        self.clients = connected_clients
        self._initialized = True

        logger.info(f"MultiMCP client initialized with {len(self.clients)} servers, "
                   f"{len(self.tools)} tools, {len(self.resources)} resources, {len(self.prompts)} prompts")


    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        async with self._disconnect_lock:
            if self._cleanup_done:
                return

            # Disconnect all clients concurrently
            if self.clients:
                disconnect_tasks = [
                    client.disconnect() 
                    for client in self.clients.values()
                ]
                
                # Wait for all disconnections, but don't fail if some have errors
                results = await asyncio.gather(*disconnect_tasks, return_exceptions=True)
                
                # Log any disconnection errors
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        server_name = list(self.clients.keys())[i]
                        logger.warning(f"Error disconnecting from {server_name}: {result}")

            self.clients.clear()
            self.tools.clear()
            self.resources.clear()
            self.prompts.clear()
            self._tool_to_client.clear()
            self._initialized = False
            self._cleanup_done = True

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool on the appropriate server.

        Args:
            tool_name: Prefixed tool name (e.g., "mcp__server__tool")
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            MCPValidationError: If tool name or arguments are invalid
            MCPError: If tool execution fails
        """
        # Validate input parameters
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise MCPValidationError(
                "Tool name must be a non-empty string",
                field="tool_name",
                value=tool_name
            )

        if not isinstance(arguments, dict):
            raise MCPValidationError(
                "Tool arguments must be a dictionary",
                field="arguments",
                value=type(arguments).__name__
            )

        # Check if tool exists
        if tool_name not in self._tool_to_client:
            available_tools = list(self.tools.keys())
            raise MCPError(
                f"Tool '{tool_name}' not available",
                context={
                    "requested_tool": tool_name,
                    "available_tools": available_tools[:10],  # Limit for readability
                    "total_available": len(available_tools)
                }
            )

        server_name = self._tool_to_client[tool_name]
        client = self.clients.get(server_name)

        if not client:
            raise MCPConnectionError(
                f"Server '{server_name}' not connected",
                server_name=server_name,
                context={"tool_name": tool_name}
            )

        # Extract original tool name (remove prefix)
        if tool_name.startswith(f"mcp__{server_name}__"):
            original_tool_name = tool_name[len(f"mcp__{server_name}__"):]
        else:
            # Fallback for non-prefixed names
            original_tool_name = tool_name

        return await client.call_tool(original_tool_name, arguments)

    async def get_resource(self, uri: str) -> Any:
        """
        Get resource content by URI from any connected server.

        Args:
            uri: Resource URI

        Returns:
            Resource content
        """
        if uri not in self.resources:
            raise MCPError(f"Resource '{uri}' not available")

        # Try each client until we find one that has the resource
        for client in self.clients.values():
            if uri in client.resources:
                return await client.get_resource(uri)

        raise MCPError(f"Resource '{uri}' not found on any server")

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """
        Get prompt template from appropriate server.

        Args:
            name: Prompt name (may be prefixed with server name)
            arguments: Prompt arguments

        Returns:
            Prompt content
        """
        if name not in self.prompts:
            raise MCPError(f"Prompt '{name}' not available")

        # Extract server name from prefixed prompt name (mcp__server__prompt format)
        if name.startswith("mcp__") and "__" in name[5:]:
            # Remove mcp__ prefix and split server__prompt
            name_without_prefix = name[5:]  # Remove "mcp__"
            server_name, original_name = name_without_prefix.split("__", 1)
            client = self.clients.get(server_name)
            if client:
                return await client.get_prompt(original_name, arguments)

        # Try each client
        for client in self.clients.values():
            if name in client.prompts:
                return await client.get_prompt(name, arguments)

        raise MCPError(f"Prompt '{name}' not found on any server")

    def get_active_sessions(self) -> List[ClientSession]:
        """
        Return active MCP ClientSession objects for all connected servers.
        These sessions are already initialized and managed by this client.
        """
        sessions: List[ClientSession] = []
        for client in self.clients.values():
            if getattr(client, "session", None) is not None:
                sessions.append(client.session)  # type: ignore[arg-type]
        return sessions

    def get_active_sessions_by_server(self, server_names: Optional[List[str]] = None) -> List[ClientSession]:
        """
        Return active ClientSession objects filtered by server names.

        Args:
            server_names: Optional list of server names to include. If None, returns all.
        """
        if server_names is None:
            return self.get_active_sessions()
        sessions: List[ClientSession] = []
        for name in server_names:
            client = self.clients.get(name)
            if client and getattr(client, "session", None) is not None:
                sessions.append(client.session)  # type: ignore[arg-type]
        return sessions

    def get_available_tools(self) -> List[str]:
        """Get list of all available tool names (with prefixes)."""
        return list(self.tools.keys())

    def get_available_resources(self) -> List[str]:
        """Get list of all available resource URIs."""
        return list(self.resources.keys())

    def get_available_prompts(self) -> List[str]:
        """Get list of all available prompt names (with prefixes)."""
        return list(self.prompts.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Perform health check on all connected MCP servers.

        Returns:
            Dictionary mapping server names to health status
        """
        health_status = {}

        for server_name, client in self.clients.items():
            try:
                is_healthy = await client.health_check()
                health_status[server_name] = is_healthy
                if not is_healthy:
                    logger.warning(f"Health check failed for server: {server_name}")
            except Exception as e:
                logger.error(f"Health check error for server {server_name}: {e}")
                health_status[server_name] = False

        healthy_count = sum(health_status.values())
        total_count = len(health_status)
        logger.info(f"Health check completed: {healthy_count}/{total_count} servers healthy")

        return health_status

    async def reconnect_failed_servers(self, max_retries: int = 3) -> Dict[str, bool]:
        """
        Attempt to reconnect any failed servers.

        Args:
            max_retries: Maximum number of reconnection attempts per server

        Returns:
            Dictionary mapping server names to reconnection success status
        """
        health_status = await self.health_check_all()
        reconnect_results = {}

        for server_name, is_healthy in health_status.items():
            if not is_healthy:
                logger.info(f"Attempting to reconnect failed server: {server_name}")
                try:
                    client = self.clients[server_name]
                    success = await client.reconnect(max_retries=max_retries)
                    reconnect_results[server_name] = success
                    if success:
                        logger.info(f"Successfully reconnected server: {server_name}")
                    else:
                        logger.error(f"Failed to reconnect server: {server_name}")
                except Exception as e:
                    logger.error(f"Reconnection error for server {server_name}: {e}")
                    reconnect_results[server_name] = False
            else:
                reconnect_results[server_name] = True  # Already healthy

        return reconnect_results

    def get_server_names(self) -> List[str]:
        """Get list of connected server names."""
        return list(self.clients.keys())

    def get_tools_by_server(self, server_name: str) -> List[str]:
        """Get list of tools for a specific server."""
        if server_name not in self.clients:
            return []
        return [name for name, client_name in self._tool_to_client.items()
                if client_name == server_name]

    def is_connected(self) -> bool:
        """Check if any servers are connected."""
        return self._initialized and len(self.clients) > 0

    async def __aenter__(self) -> "MultiMCPClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        _exc_type: Optional[type],
        _exc_val: Optional[BaseException],
        _exc_tb: Optional[TracebackType],
    ) -> None:
        """Async context manager exit."""
        await self.disconnect()

    @classmethod
    async def create_and_connect(
        cls,
        server_configs: List[Dict[str, Any]],
        *,
        timeout_seconds: int = 30,
        allowed_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ) -> "MultiMCPClient":
        """
        Create and connect MultiMCP client in one step.

        Args:
            server_configs: List of server configuration dictionaries
            timeout_seconds: Timeout for operations in seconds
            allowed_tools: Optional list of tool names to include
            exclude_tools: Optional list of tool names to exclude

        Returns:
            Connected MultiMCPClient instance
        """
        client = cls(
            server_configs,
            timeout_seconds=timeout_seconds,
            allowed_tools=allowed_tools,
            exclude_tools=exclude_tools,
        )
        await client.connect()
        return client