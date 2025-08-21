"""
MCP client implementation for connecting to MCP servers. This module provides enhanced MCP client functionality to connect with MCP servers and integrate external tools and resources into the MassGen workflow.
"""
import asyncio
import logging
import weakref
from datetime import timedelta
from types import TracebackType
from typing import Dict, List, Any, Optional

from .exceptions import (
    MCPError, MCPConnectionError, MCPServerError,
    MCPValidationError, MCPTimeoutError
)
from .security import (
    validate_server_config, sanitize_tool_name, prepare_command,
    validate_tool_arguments
)

# Import official MCP library components
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp import types as mcp_types

# Set up logging
logger = logging.getLogger(__name__)


class MCPClient:
    """
    Enhanced MCP client for communicating with MCP servers.

    Supports both official MCP library and fallback custom implementation.
    Provides improved security, error handling, and async context management.
    """

    def __init__(
        self,
        server_config: Dict[str, Any],
        *,
        timeout_seconds: int = 30,
        include_tools: Optional[List[str]] = None,
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
                - cwd: Working directory (for stdio)
                - args: Additional command arguments (for stdio)
                - headers: HTTP headers (for streamable-http)
            timeout_seconds: Timeout for operations in seconds
            include_tools: Optional list of tool names to include (if None, includes all)
            exclude_tools: Optional list of tool names to exclude (if None, excludes none)
        """
        # Validate and sanitize configuration
        self.config = validate_server_config(server_config)
        self.name = self.config["name"]
        self.timeout_seconds = timeout_seconds
        self.include_tools = include_tools
        self.exclude_tools = exclude_tools
        # Always use official library (no fallback)
        self.use_official_library = True

        # Tool storage using official MCP types
        self.tools: Dict[str, mcp_types.Tool] = {}
        self.resources: Dict[str, mcp_types.Resource] = {}
        self.prompts: Dict[str, mcp_types.Prompt] = {}

        # Connection management
        self.session: Optional[ClientSession] = None
        self._initialized = False

        # Background manager for owning transport/session contexts
        self._manager_task: Optional[asyncio.Task] = None
        self._connected_event: asyncio.Event = asyncio.Event()
        self._disconnect_event: asyncio.Event = asyncio.Event()

        # Setup cleanup logic
        def cleanup():
            """Clean up resources on finalization"""
            try:
                # Note: Cannot call async methods from finalizer
                # Session cleanup will be handled by async context managers
                logger.debug(f"Cleanup finalizer called for MCPClient {self.name}")
            except Exception as e:
                # Finalizers should not raise exceptions
                logger.warning(f"Error in cleanup finalizer for {self.name}: {e}")

        self._cleanup_finalizer = weakref.finalize(self, cleanup)

    # Removed fallback transport creation - using official library only

    async def connect(self) -> None:
        """Connect to MCP server and discover capabilities using a background manager task.

        Ensures transport contexts are entered and exited within the same task
        to satisfy anyio CancelScope requirements.
        """
        if self._initialized or (self._manager_task and not self._manager_task.done()):
            logger.debug(f"Client {self.name} already connected")
            return

        logger.info(f"Connecting to MCP server: {self.name}")

        # Reset events for a new connection attempt
        self._connected_event = asyncio.Event()
        self._disconnect_event = asyncio.Event()

        # Start background manager task
        self._manager_task = asyncio.create_task(self._run_manager())

        # Wait until manager signals readiness (or failure)
        await self._connected_event.wait()

        if not self.session or not self._initialized:
            # Background task failed early
            err: BaseException | None = None
            if self._manager_task:
                try:
                    await self._manager_task
                except Exception as e:  # pragma: no cover - surfaced below
                    err = e
            await self.disconnect()
            raise MCPConnectionError(
                f"Failed to connect to MCP server {self.name}: {err or 'unknown error'}"
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
            timeout = self.config.get("timeout", timedelta(seconds=self.timeout_seconds))
            sse_read_timeout = self.config.get("sse_read_timeout", timedelta(seconds=60 * 5))

            logger.debug(f"Setting up streamable-http transport for {self.name}: url={url}")

            if isinstance(timeout, (int, float)):
                timeout = timedelta(seconds=timeout)
            if isinstance(sse_read_timeout, (int, float)):
                sse_read_timeout = timedelta(seconds=sse_read_timeout)

            return streamablehttp_client(
                url=url,
                headers=headers,
                timeout=timeout,
                sse_read_timeout=sse_read_timeout
            )
        else:
            raise MCPConnectionError(f"Unsupported transport type: {transport_type}")

    async def _run_manager(self) -> None:
        """Background task that owns the transport and session contexts."""
        try:
            transport_ctx = self._create_transport_context()

            async with transport_ctx as session_params:
                read, write = session_params[0:2]

                async with ClientSession(
                    read, write,
                    read_timeout_seconds=timedelta(seconds=self.timeout_seconds)
                ) as session:
                    # Initialize and expose session
                    self.session = session
                    await self.session.initialize()
                    await self._discover_capabilities()
                    self._initialized = True
                    self._connected_event.set()

                    # Wait until disconnect is requested
                    await self._disconnect_event.wait()

        except Exception as e:
            logger.error(f"MCP manager error for {self.name}: {e}", exc_info=True)
            # Ensure waiters are released even on failure
            if not self._connected_event.is_set():
                self._connected_event.set()
        finally:
            # Clear session state
            self._initialized = False
            self.session = None

    async def disconnect(self) -> None:
        """Disconnect from MCP server.

        Signals the background manager task to exit so that
        async contexts are closed in the same task where they were opened.
        """
        if self._manager_task and not self._manager_task.done():
            self._disconnect_event.set()
            try:
                await self._manager_task
            finally:
                self._manager_task = None
                # Reset events for potential future connections
                self._connected_event = asyncio.Event()
                self._disconnect_event = asyncio.Event()

        self._initialized = False

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

        # List tools
        try:
            available_tools = await self.session.list_tools()

            # Filter tools based on include/exclude lists
            for tool in available_tools.tools:
                if self.exclude_tools and tool.name in self.exclude_tools:
                    continue
                if self.include_tools is None or tool.name in self.include_tools:
                    # Use the official MCP Tool type directly
                    self.tools[tool.name] = tool
        except Exception as e:
            logger.warning(f"Failed to list tools for {self.name}: {e}")

        # List resources (optional)
        try:
            available_resources = await self.session.list_resources()
            for resource in available_resources.resources:
                # Use the official MCP Resource type directly
                self.resources[resource.uri] = resource
        except Exception:
            # Resources not supported by this server
            pass

        # List prompts (optional)
        try:
            available_prompts = await self.session.list_prompts()
            for prompt in available_prompts.prompts:
                # Use the official MCP Prompt type directly
                self.prompts[prompt.name] = prompt
        except Exception:
            # Prompts not supported by this server
            pass

    # Removed fallback discovery methods - using official library only

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
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ):
        """
        Initialize MultiMCP client.

        Args:
            server_configs: List of server configuration dictionaries
            timeout_seconds: Timeout for operations in seconds
            include_tools: Optional list of tool names to include (if None, includes all)
            exclude_tools: Optional list of tool names to exclude (if None, excludes none)
        """
        self.server_configs = [validate_server_config(config) for config in server_configs]
        self.timeout_seconds = timeout_seconds
        self.include_tools = include_tools
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

    async def connect(self) -> None:
        """Connect to all MCP servers and discover capabilities."""
        async with self._connection_lock:
            if self._initialized:
                return

            await self._connect_all()

    async def _connect_all(self) -> None:
        """Connect to all configured MCP servers."""
        if self._initialized:
            return

        connected_clients = {}
        
        for server_config in self.server_configs:
            server_name = server_config["name"]
            try:
                # Create client for this server
                client = MCPClient(
                    server_config,
                    timeout_seconds=self.timeout_seconds,
                    include_tools=self.include_tools,
                    exclude_tools=self.exclude_tools,
                )

                # Connect the client (this will start its background manager)
                await client.connect()
                connected_clients[server_name] = client

                # Register tools with server prefix
                for tool_name, tool in client.tools.items():
                    prefixed_name = sanitize_tool_name(tool_name, server_name)
                    self.tools[prefixed_name] = tool
                    self._tool_to_client[prefixed_name] = server_name

                # Register resources
                for uri, resource in client.resources.items():
                    self.resources[uri] = resource

                # Register prompts with server prefix
                for prompt_name, prompt in client.prompts.items():
                    prefixed_name = f"{server_name}__{prompt_name}"
                    self.prompts[prefixed_name] = prompt

                print(f"[MultiMCP] Connected to server '{server_name}' with {len(client.tools)} tools")

            except Exception as e:
                print(f"[MultiMCP] Failed to connect to server '{server_name}': {e}")
                # Continue with other servers
                continue

        # Only set clients dict after all connections are attempted
        self.clients = connected_clients
        self._initialized = True

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
        """
        if tool_name not in self._tool_to_client:
            raise MCPError(f"Tool '{tool_name}' not available")

        server_name = self._tool_to_client[tool_name]
        client = self.clients.get(server_name)

        if not client:
            raise MCPError(f"Server '{server_name}' not connected")

        # Extract original tool name (remove prefix)
        original_tool_name = tool_name.replace(f"mcp__{server_name}__", "")

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

        # Extract server name from prefixed prompt name
        if "__" in name:
            server_name, original_name = name.split("__", 1)
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
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
    ) -> "MultiMCPClient":
        """
        Create and connect MultiMCP client in one step.

        Args:
            server_configs: List of server configuration dictionaries
            timeout_seconds: Timeout for operations in seconds
            include_tools: Optional list of tool names to include
            exclude_tools: Optional list of tool names to exclude

        Returns:
            Connected MultiMCPClient instance
        """
        client = cls(
            server_configs,
            timeout_seconds=timeout_seconds,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
        )
        await client.connect()
        return client