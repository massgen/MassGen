"""
Core MCP integration utilities for stdio and streamable-http transports.
Excludes HTTP transport (provider-specific).
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# Import MCP components
try:
    from .client import MultiMCPClient
    from .backend_utils import Function, MCPErrorHandler
    from .exceptions import (
        MCPError, MCPConnectionError, MCPTimeoutError, MCPServerError,
        MCPValidationError
    )
except ImportError as e:
    logger.debug(f"MCP import failed: {e}")
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
    def normalize_mcp_servers(servers: Any) -> List[Dict[str, Any]]:
        """Validate and normalize mcp_servers into a list of dicts.
        
        Args:
            servers: MCP servers configuration (list, dict, or None)
            
        Returns:
            Normalized list of server dictionaries
        """
        if not servers:
            return []
        
        if isinstance(servers, dict):
            servers = [servers]
        
        if not isinstance(servers, list):
            logger.warning(f"Invalid mcp_servers type: {type(servers)}, expected list or dict")
            return []
        
        normalized = []
        for i, server in enumerate(servers):
            if not isinstance(server, dict):
                logger.warning(f"Skipping invalid server at index {i}: {server}")
                continue
            
            if "type" not in server:
                logger.warning(f"Server at index {i} missing 'type' field")
                continue
            
            # Add default name if missing
            if "name" not in server:
                server = server.copy()
                server["name"] = f"server_{i}"
            
            normalized.append(server)
        
        return normalized
    
    @staticmethod
    def separate_stdio_streamable_servers(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract only stdio and streamable-http servers.
        
        Args:
            servers: List of server configurations
            
        Returns:
            List containing only stdio and streamable-http servers
        """
        stdio_streamable = []
        
        for server in servers:
            transport_type = server.get("type", "").lower()
            if transport_type in ["stdio", "streamable-http"]:
                stdio_streamable.append(server)
            else:
                logger.debug(f"Excluding {transport_type} server '{server.get('name', 'unnamed')}' from stdio/streamable-http processing")
        
        return stdio_streamable
    
    @staticmethod
    async def setup_mcp_client(
        servers: List[Dict[str, Any]], 
        allowed_tools: Optional[List[str]], 
        exclude_tools: Optional[List[str]],
        circuit_breaker = None,
        timeout_seconds: int = 30
    ) -> Optional[MultiMCPClient]:
        """Setup MCP client for stdio/streamable-http servers with circuit breaker protection.
        
        Args:
            servers: List of server configurations
            allowed_tools: Optional list of allowed tool names
            exclude_tools: Optional list of excluded tool names
            circuit_breaker: Optional circuit breaker for failure tracking
            timeout_seconds: Connection timeout in seconds
            
        Returns:
            Connected MultiMCPClient or None if setup failed
        """
        if MultiMCPClient is None:
            logger.warning("MultiMCPClient not available, MCP functionality disabled")
            return None
        
        # Normalize and filter servers
        normalized_servers = MCPIntegrationManager.normalize_mcp_servers(servers)
        stdio_streamable_servers = MCPIntegrationManager.separate_stdio_streamable_servers(normalized_servers)
        
        if not stdio_streamable_servers:
            logger.debug("No stdio/streamable-http servers configured")
            return None
        
        # Apply circuit breaker filtering if available
        if circuit_breaker:
            filtered_servers = MCPIntegrationManager.apply_circuit_breaker_filtering(
                stdio_streamable_servers, circuit_breaker
            )
        else:
            filtered_servers = stdio_streamable_servers
        
        if not filtered_servers:
            logger.warning("All stdio/streamable-http servers filtered out by circuit breaker")
            return None
        
        # Retry logic with exponential backoff
        max_retries = 3
        for retry in range(max_retries):
            try:
                if retry > 0:
                    delay = MCPErrorHandler.get_retry_delay(retry - 1)
                    logger.info(f"MCP connection retry {retry}/{max_retries - 1} after {delay:.2f}s")
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
                        filtered_servers, "success", circuit_breaker
                    )
                
                logger.info(f"MCP connection successful on attempt {retry + 1}")
                return client
                
            except (MCPConnectionError, MCPTimeoutError, MCPServerError) as e:
                if retry < max_retries - 1:  # Not last attempt
                    MCPErrorHandler.log_error(e, f"MCP connection attempt {retry + 1}")
                    continue
                    
                # Record failure and re-raise
                if circuit_breaker:
                    await MCPIntegrationManager.record_circuit_breaker_event(
                        filtered_servers, "failure", circuit_breaker, str(e)
                    )
                
                MCPErrorHandler.log_error(e, f"MCP connection failed after {max_retries} attempts", "error")
                return None
            except Exception as e:
                MCPErrorHandler.log_error(e, f"Unexpected error during MCP connection attempt {retry + 1}", "error")
                if retry < max_retries - 1:
                    continue
                return None
        
        return None
    
    @staticmethod
    def convert_tools_to_functions(mcp_client) -> Dict[str, Function]:
        """Convert MCP tools to Function objects with standardized closure pattern.
        
        Args:
            mcp_client: Connected MultiMCPClient instance
            
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
                            logger.error(f"Invalid JSON arguments for MCP tool {captured_tool_name}: {e}")
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
                logger.error(f"Failed to register MCP tool {tool_name}: {e}")
        
        logger.info(f"Registered {len(functions)} MCP tools as Function objects")
        return functions
    
    @staticmethod
    def apply_circuit_breaker_filtering(servers: List[Dict], circuit_breaker) -> List[Dict]:
        """Apply circuit breaker filtering to stdio/streamable-http servers.
        
        Args:
            servers: List of server configurations
            circuit_breaker: Circuit breaker instance
            
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
                logger.debug(f"Circuit breaker: Skipping server {server_name} (circuit open)")
        
        return filtered_servers
    
    @staticmethod
    async def record_circuit_breaker_event(
        servers: List[Dict], 
        event: str, 
        circuit_breaker, 
        error_msg: Optional[str] = None
    ) -> None:
        """Record circuit breaker events for stdio/streamable-http servers.
        
        Args:
            servers: List of server configurations
            event: Event type ("success" or "failure")
            circuit_breaker: Circuit breaker instance
            error_msg: Optional error message for failure events
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
                logger.warning(f"Circuit breaker record_{event} failed for server {server_name}: {cb_error}")
        
        if count > 0:
            if event == "success":
                logger.debug(f"Circuit breaker: Recorded success for {count} servers")
            else:
                logger.warning(f"Circuit breaker: Recorded failure for {count} servers. Error: {error_msg}")
    
    @staticmethod
    async def cleanup_mcp_client(client) -> None:
        """Clean up MCP client connections.
        
        Args:
            client: MultiMCPClient instance to clean up
        """
        if client:
            try:
                await client.cleanup()
                logger.debug("MCP client cleanup completed")
            except Exception as e:
                logger.warning(f"Error during MCP client cleanup: {e}")
