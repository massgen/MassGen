"""
Core MCP integration utilities for stdio and streamable-http transports.
Excludes HTTP transport (provider-specific).
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
import asyncio
import json
from ..logger_config import logger, log_backend_activity


def _log_mcp_activity(backend_name: Optional[str], message: str, details: Dict[str, Any], agent_id: Optional[str] = None) -> None:
    """Log MCP activity with backend context if available."""
    if backend_name:
        log_backend_activity(backend_name, f"MCP: {message}", details, agent_id=agent_id)
    else:
        logger.info(f"MCP {message}", extra=details)

# Import MCP components
try:
    from .client import MultiMCPClient
    from .backend_utils import Function, MCPErrorHandler
    from .exceptions import (
        MCPError, MCPConnectionError, MCPTimeoutError, MCPServerError,
        MCPValidationError
    )
except ImportError as e:
    logger.error("MCP import failed", extra={"error": str(e)})
    MultiMCPClient = None
    Function = None
    MCPErrorHandler = None
    MCPError = Exception
    MCPConnectionError = ConnectionError
    MCPTimeoutError = TimeoutError
    MCPServerError = Exception
    MCPValidationError = ValueError


class MCPIntegrationManager:
    """Centralized MCP integration management for stdio/streamable-http only."""
    
    @staticmethod
    def normalize_mcp_servers(servers: Any, backend_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Validate and normalize mcp_servers into a list of dicts.

        Args:
            servers: MCP servers configuration (list, dict, or None)
            backend_name: Optional backend name for logging context

        Returns:
            Normalized list of server dictionaries
        """
        if not servers:
            return []

        if isinstance(servers, dict):
            servers = [servers]

        if not isinstance(servers, list):
            _log_mcp_activity(backend_name, "invalid mcp_servers type", {"type": type(servers).__name__, "expected": "list or dict"})
            return []

        normalized = []
        for i, server in enumerate(servers):
            if not isinstance(server, dict):
                _log_mcp_activity(backend_name, "skipping invalid server", {"index": i, "server": str(server)})
                continue

            if "type" not in server:
                _log_mcp_activity(backend_name, "server missing type field", {"index": i})
                continue

            # Add default name if missing
            if "name" not in server:
                server = server.copy()
                server["name"] = f"server_{i}"

            normalized.append(server)

        return normalized
    
    @staticmethod
    def separate_stdio_streamable_servers(servers: List[Dict[str, Any]], backend_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract only stdio and streamable-http servers.

        Args:
            servers: List of server configurations
            backend_name: Optional backend name for logging context

        Returns:
            List containing only stdio and streamable-http servers
        """
        stdio_streamable = []

        for server in servers:
            transport_type = server.get("type", "").lower()
            if transport_type in ["stdio", "streamable-http"]:
                stdio_streamable.append(server)
            else:
                _log_mcp_activity(backend_name, "excluding server from stdio/streamable-http processing", {"transport_type": transport_type, "server_name": server.get('name', 'unnamed')})

        return stdio_streamable
    
    @staticmethod
    async def setup_mcp_client(
        servers: List[Dict[str, Any]],
        allowed_tools: Optional[List[str]],
        exclude_tools: Optional[List[str]],
        circuit_breaker = None,
        timeout_seconds: int = 30,
        backend_name: Optional[str] = None
    ) -> Optional[MultiMCPClient]:
        """Setup MCP client for stdio/streamable-http servers with circuit breaker protection.

        Args:
            servers: List of server configurations
            allowed_tools: Optional list of allowed tool names
            exclude_tools: Optional list of excluded tool names
            circuit_breaker: Optional circuit breaker for failure tracking
            timeout_seconds: Connection timeout in seconds
            backend_name: Optional backend name for logging context

        Returns:
            Connected MultiMCPClient or None if setup failed
        """
        if MultiMCPClient is None:
            _log_mcp_activity(backend_name, "MultiMCPClient unavailable", {"functionality": "disabled"})
            return None

        # Normalize and filter servers
        normalized_servers = MCPIntegrationManager.normalize_mcp_servers(servers, backend_name)
        stdio_streamable_servers = MCPIntegrationManager.separate_stdio_streamable_servers(normalized_servers, backend_name)

        if not stdio_streamable_servers:
            _log_mcp_activity(backend_name, "no stdio/streamable-http servers configured", {})
            return None
        
        # Apply circuit breaker filtering if available
        if circuit_breaker:
            filtered_servers = MCPIntegrationManager.apply_circuit_breaker_filtering(
                stdio_streamable_servers, circuit_breaker, backend_name
            )
        else:
            filtered_servers = stdio_streamable_servers

        if not filtered_servers:
            _log_mcp_activity(backend_name, "all servers filtered by circuit breaker", {"transport_types": ["stdio", "streamable-http"]})
            return None
        
        # Retry logic with exponential backoff
        max_retries = 3
        for retry in range(max_retries):
            try:
                if retry > 0:
                    delay = MCPErrorHandler.get_retry_delay(retry - 1)
                    _log_mcp_activity(backend_name, "connection retry", {"attempt": retry, "max_retries": max_retries - 1, "delay_seconds": delay})
                    await asyncio.sleep(delay)
                
                client = await MultiMCPClient.create_and_connect(
                    filtered_servers,
                    timeout_seconds=timeout_seconds,
                    allowed_tools=allowed_tools,
                    exclude_tools=exclude_tools
                )
                
                # Record success in circuit breaker
                if circuit_breaker:
                    await MCPIntegrationManager.record_circuit_breaker_event(
                        filtered_servers, "success", circuit_breaker, backend_name=backend_name
                    )

                _log_mcp_activity(backend_name, "connection successful", {"attempt": retry + 1})
                return client
                
            except (MCPConnectionError, MCPTimeoutError, MCPServerError) as e:
                if retry < max_retries - 1:  # Not last attempt
                    MCPErrorHandler.log_error(e, f"MCP connection attempt {retry + 1}")
                    continue
                    
                # Record failure and re-raise
                if circuit_breaker:
                    await MCPIntegrationManager.record_circuit_breaker_event(
                        filtered_servers, "failure", circuit_breaker, str(e), backend_name
                    )

                _log_mcp_activity(backend_name, "connection failed after retries", {"max_retries": max_retries, "error": str(e)})
                return None
            except Exception as e:
                MCPErrorHandler.log_error(e, f"Unexpected error during MCP connection attempt {retry + 1}", "error")
                if retry < max_retries - 1:
                    continue
                return None
        
        return None
    
    @staticmethod
    def convert_tools_to_functions(mcp_client, backend_name: Optional[str] = None) -> Dict[str, Function]:
        """Convert MCP tools to Function objects with standardized closure pattern.

        Args:
            mcp_client: Connected MultiMCPClient instance
            backend_name: Optional backend name for logging context

        Returns:
            Dictionary mapping tool names to Function objects
        """
        if not mcp_client or not hasattr(mcp_client, 'tools'):
            return {}

        functions = {}

        for tool_name, tool in mcp_client.tools.items():
            try:
                # Fix closure bug by using default parameter to capture tool_name
                def create_tool_entrypoint(captured_tool_name: str = tool_name):
                    async def tool_entrypoint(input_str: str) -> Any:
                        try:
                            arguments = json.loads(input_str)
                        except (json.JSONDecodeError, ValueError) as e:
                            _log_mcp_activity(backend_name, "invalid JSON arguments for tool", {"tool_name": captured_tool_name, "error": str(e)})
                            raise MCPValidationError(
                                f"Invalid JSON arguments for tool {captured_tool_name}: {e}",
                                field="arguments",
                                value=input_str
                            )
                        return await mcp_client.call_tool(captured_tool_name, arguments)
                    return tool_entrypoint

                entrypoint = create_tool_entrypoint()
                function = Function(
                    name=tool_name,
                    description=tool.description,
                    parameters=tool.inputSchema,
                    entrypoint=entrypoint,
                )
                functions[function.name] = function

            except Exception as e:
                _log_mcp_activity(backend_name, "failed to register tool", {"tool_name": tool_name, "error": str(e)})

        _log_mcp_activity(backend_name, "registered tools as Function objects", {"tool_count": len(functions)})
        return functions
    
    @staticmethod
    def apply_circuit_breaker_filtering(servers: List[Dict], circuit_breaker, backend_name: Optional[str] = None) -> List[Dict]:
        """Apply circuit breaker filtering to stdio/streamable-http servers.

        Args:
            servers: List of server configurations
            circuit_breaker: Circuit breaker instance
            backend_name: Optional backend name for logging context

        Returns:
            List of servers that pass circuit breaker filtering
        """
        if not circuit_breaker:
            return servers

        filtered_servers = []
        for server in servers:
            server_name = server.get("name", "unnamed")
            if not circuit_breaker.should_skip_server(server_name):
                filtered_servers.append(server)
            else:
                _log_mcp_activity(backend_name, "circuit breaker skipping server", {"server_name": server_name, "reason": "circuit_open"})

        return filtered_servers
    
    @staticmethod
    async def record_circuit_breaker_event(
        servers: List[Dict],
        event: str,
        circuit_breaker,
        error_msg: Optional[str] = None,
        backend_name: Optional[str] = None
    ) -> None:
        """Record circuit breaker events for stdio/streamable-http servers.

        Args:
            servers: List of server configurations
            event: Event type ("success" or "failure")
            circuit_breaker: Circuit breaker instance
            error_msg: Optional error message for failure events
            backend_name: Optional backend name for logging context
        """
        if not circuit_breaker:
            return

        count = 0
        for server in servers:
            server_name = server.get("name", "unnamed")
            try:
                if event == "success":
                    circuit_breaker.record_success(server_name)
                else:
                    circuit_breaker.record_failure(server_name)
                count += 1
            except Exception as cb_error:
                _log_mcp_activity(backend_name, "circuit breaker record failed", {"event": event, "server_name": server_name, "error": str(cb_error)})

        if count > 0:
            if event == "success":
                _log_mcp_activity(backend_name, "circuit breaker recorded success", {"server_count": count})
            else:
                _log_mcp_activity(backend_name, "circuit breaker recorded failure", {"server_count": count, "error": error_msg})
    
    @staticmethod
    async def cleanup_mcp_client(client, backend_name: Optional[str] = None) -> None:
        """Clean up MCP client connections.

        Args:
            client: MultiMCPClient instance to clean up
            backend_name: Optional backend name for logging context
        """
        if client:
            try:
                await client.cleanup()
                _log_mcp_activity(backend_name, "client cleanup completed", {})
            except Exception as e:
                _log_mcp_activity(backend_name, "error during client cleanup", {"error": str(e)})

