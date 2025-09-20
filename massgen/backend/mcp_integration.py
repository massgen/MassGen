"""
MCP (Model Context Protocol) Integration Mixin
Provides unified MCP functionality for all backends that support MCP.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Any, Optional, Set
from ..logger_config import logger

# MCP integration imports with fallback
try:
    from ..mcp_tools import (
        MultiMCPClient,
        MCPError,
        MCPConnectionError,
        MCPCircuitBreaker,
        MCPConfigurationError,
        MCPValidationError,
        MCPTimeoutError,
        MCPServerError,
        MCPConfigValidator,
        MCPErrorHandler,
        MCPSetupManager,
        MCPResourceManager,
        MCPExecutionManager,
        MCPRetryHandler,
        MCPMessageManager,
        MCPConfigHelper,
        MCPCircuitBreakerManager,
        Function,
    )
    MCP_AVAILABLE = True
except ImportError as e:
    logger.warning(f"MCP import failed: {e}")
    MCP_AVAILABLE = False
    # Create fallback assignments
    MultiMCPClient = None
    MCPCircuitBreaker = None
    Function = None
    MCPConfigValidator = None
    MCPErrorHandler = None
    MCPSetupManager = None
    MCPResourceManager = None
    MCPExecutionManager = None
    MCPRetryHandler = None
    MCPMessageManager = None
    MCPConfigHelper = None
    MCPCircuitBreakerManager = None
    MCPError = ImportError
    MCPConnectionError = ImportError
    MCPConfigurationError = ImportError
    MCPValidationError = ImportError
    MCPTimeoutError = ImportError
    MCPServerError = ImportError


class MCPIntegrationMixin:
    """Mixin class providing MCP integration functionality."""
    
    def _init_mcp_integration(self, **kwargs):
        """
        Initialize MCP integration components.
        Should be called from backend's __init__ method.
        
        Args:
            **kwargs: Configuration parameters including:
                - mcp_servers: List of MCP server configurations
                - allowed_tools: Optional list of allowed tool names
                - exclude_tools: Optional list of excluded tool names
                - max_mcp_message_history: Maximum message history size
                - agent_id: Agent identifier for logging
        """
        # MCP configuration
        self.mcp_servers = kwargs.get("mcp_servers", [])
        self.allowed_tools = kwargs.get("allowed_tools", None)
        self.exclude_tools = kwargs.get("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False
        
        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_function_names: Set[str] = set()
        
        # Circuit breakers
        self._mcp_tools_circuit_breaker = None
        self._circuit_breakers_enabled = MCP_AVAILABLE and MCPCircuitBreaker is not None
        
        # Function registry for mcp_tools-based servers
        self.functions: Dict[str, Function] = {}
        
        # Thread safety for counters
        self._stats_lock = asyncio.Lock()
        
        # Message history limit
        self._max_mcp_message_history = kwargs.get("max_mcp_message_history", 200)
        
        # Backend identification
        self.backend_name = getattr(self, "get_provider_name", lambda: "Unknown")()
        self.agent_id = kwargs.get("agent_id", None)
        
        # Initialize circuit breakers if available
        self._setup_circuit_breakers()
    
    def _setup_circuit_breakers(self):
        """Setup circuit breakers for MCP tools."""
        if not self._circuit_breakers_enabled:
            logger.warning(
                "Circuit breakers not available - proceeding without circuit breaker protection"
            )
            return
        
        try:
            # Use shared utility to build circuit breaker configuration
            mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools")
            
            if mcp_tools_config:
                self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
                logger.info("Circuit breaker initialized for MCP tools")
            else:
                logger.warning(
                    "MCP tools circuit breaker config not available, disabling circuit breaker functionality"
                )
                self._circuit_breakers_enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize circuit breakers: {e}")
            self._circuit_breakers_enabled = False
    
    async def _initialize_mcp_client(self) -> bool:
        """
        Initialize the MCP client with configured servers.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        if self._mcp_initialized or not self.mcp_servers:
            return self._mcp_initialized
        
        if not MCP_AVAILABLE:
            logger.warning("MCP not available - skipping MCP client initialization")
            return False
        
        try:
            logger.info(f"Initializing MCP client with {len(self.mcp_servers)} servers")
            
            # Initialize MultiMCPClient
            self._mcp_client = MultiMCPClient(
                mcp_servers=self.mcp_servers,
                backend_name=self.backend_name,
                agent_id=self.agent_id
            )
            
            # Connect to all servers
            await self._mcp_client.connect_all()
            
            # Get available functions
            self.functions = await self._mcp_client.list_all_functions()
            self._mcp_function_names = set(self.functions.keys())
            
            logger.info(f"MCP client initialized with {len(self.functions)} functions")
            self._mcp_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}")
            self._mcp_initialized = False
            return False
    
    async def _execute_mcp_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        extract_name_func=None,
        extract_args_func=None,
        extract_id_func=None
    ) -> List[Dict[str, Any]]:
        """
        Execute MCP tool calls and return results.
        
        Args:
            tool_calls: List of tool calls to execute
            extract_name_func: Optional function to extract tool name
            extract_args_func: Optional function to extract tool arguments
            extract_id_func: Optional function to extract tool call ID
            
        Returns:
            List of tool result dictionaries
        """
        if not self._mcp_initialized or not self._mcp_client:
            logger.warning("MCP not initialized, cannot execute tools")
            return []
        
        results = []
        
        # Use default extractors if not provided
        if extract_name_func is None:
            extract_name_func = lambda tc: tc.get("function", {}).get("name", "unknown")
        if extract_args_func is None:
            extract_args_func = lambda tc: tc.get("function", {}).get("arguments", {})
        if extract_id_func is None:
            extract_id_func = lambda tc: tc.get("id", "")
        
        for tool_call in tool_calls:
            tool_name = extract_name_func(tool_call)
            tool_args = extract_args_func(tool_call)
            tool_id = extract_id_func(tool_call)
            
            # Check if this is an MCP tool
            if tool_name not in self._mcp_function_names:
                continue
            
            try:
                # Update statistics
                async with self._stats_lock:
                    self._mcp_tool_calls_count += 1
                
                # Execute with circuit breaker if available
                if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                    result = await self._mcp_tools_circuit_breaker.call(
                        self._mcp_client.call_function,
                        tool_name,
                        tool_args
                    )
                else:
                    result = await self._mcp_client.call_function(tool_name, tool_args)
                
                results.append({
                    "tool_call_id": tool_id,
                    "content": str(result),
                    "tool_name": tool_name
                })
                
            except Exception as e:
                logger.error(f"MCP tool execution failed for {tool_name}: {e}")
                async with self._stats_lock:
                    self._mcp_tool_failures += 1
                
                results.append({
                    "tool_call_id": tool_id,
                    "content": f"Error executing {tool_name}: {str(e)}",
                    "tool_name": tool_name,
                    "error": True
                })
        
        return results
    
    async def _shutdown_mcp(self):
        """Cleanup MCP resources."""
        if self._mcp_client:
            try:
                await self._mcp_client.disconnect_all()
                logger.info("MCP client disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting MCP client: {e}")
            finally:
                self._mcp_client = None
                self._mcp_initialized = False
                self.functions.clear()
                self._mcp_function_names.clear()
    
    def _filter_mcp_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter tools based on allowed/excluded lists and MCP availability.
        
        Args:
            tools: List of tool definitions
            
        Returns:
            Filtered list of tools
        """
        if not tools:
            return []
        
        filtered = []
        for tool in tools:
            # Extract tool name based on format
            if "function" in tool:
                tool_name = tool.get("function", {}).get("name", "")
            else:
                tool_name = tool.get("name", "")
            
            # Apply filtering
            if self.allowed_tools and tool_name not in self.allowed_tools:
                continue
            if self.exclude_tools and tool_name in self.exclude_tools:
                continue
            
            # Check if MCP tool is available
            if self._mcp_initialized and tool_name in self._mcp_function_names:
                filtered.append(tool)
            elif not self._mcp_initialized:
                # If MCP not initialized, include non-MCP tools
                filtered.append(tool)
        
        return filtered
    
    def get_mcp_stats(self) -> Dict[str, Any]:
        """
        Get MCP execution statistics.
        
        Returns:
            Dictionary with MCP stats
        """
        return {
            "mcp_initialized": self._mcp_initialized,
            "mcp_tool_calls": self._mcp_tool_calls_count,
            "mcp_tool_failures": self._mcp_tool_failures,
            "mcp_functions_available": len(self._mcp_function_names),
            "circuit_breakers_enabled": self._circuit_breakers_enabled
        }