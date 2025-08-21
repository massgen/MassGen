"""
MCP client implementation using the official Python MCP SDK.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool, Resource, Prompt

from .exceptions import MCPError, MCPConnectionError, MCPServerError

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """MCP tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class MCPResource:
    """MCP resource definition."""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


@dataclass
class MCPPrompt:
    """MCP prompt template definition."""
    name: str
    description: str
    arguments: Optional[List[Dict[str, Any]]] = None


class MCPClientSDK:
    """MCP client using the official Python SDK."""

    def __init__(self, server_config: Dict[str, Any]):
        """
        Initialize MCP client.
        
        Args:
            server_config: Server configuration dict
        """
        self.config = server_config
        self.name = server_config.get("name", "mcp_server")
        self.session: Optional[ClientSession] = None
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.prompts: Dict[str, MCPPrompt] = {}
        self._stdio_client = None
        self._read_stream = None
        self._write_stream = None
        self._creation_task = None
        
    async def connect(self) -> None:
        """Connect to MCP server and discover capabilities."""
        try:
            # Track the task that creates the connection
            self._creation_task = asyncio.current_task()
            
            # Get server parameters
            command = self.config.get("command", [])
            args = self.config.get("args", [])
            env = self.config.get("env", {})
            cwd = self.config.get("cwd")
            
            # Handle different command formats
            if isinstance(command, str):
                full_command = [command] + args
            elif isinstance(command, list):
                full_command = command + args
            else:
                full_command = args
                
            # Create server parameters
            server_params = StdioServerParameters(
                command=full_command[0] if full_command else "python",
                args=full_command[1:] if len(full_command) > 1 else [],
                env=env,
                cwd=cwd
            )
            
            # Create and start stdio client
            self._stdio_client = stdio_client(server_params)
            self._read_stream, self._write_stream = await self._stdio_client.__aenter__()
            
            # Create session
            self.session = ClientSession(self._read_stream, self._write_stream)
            await self.session.__aenter__()
            
            # Initialize session
            await self.session.initialize()
            
            # Discover capabilities
            await self._discover_capabilities()
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        # Handle cleanup in reverse order of connection
        # and catch exceptions to avoid cascading failures
        
        # Clean up session first
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Session cleanup error (may be expected during shutdown): {e}")
            finally:
                self.session = None
        
        # Clean up stdio client - wrapped in shield to prevent cancellation issues
        if self._stdio_client:
            try:
                # Check if we're in the same task that created the context
                # If not, we can't properly exit the context manager
                current_task = asyncio.current_task()
                if hasattr(self, '_creation_task') and current_task != self._creation_task:
                    # Different task - just clear the references
                    logger.debug("Skipping stdio_client cleanup - different task context")
                else:
                    # Same task or no task tracking - attempt normal cleanup
                    await asyncio.shield(self._stdio_client.__aexit__(None, None, None))
            except RuntimeError as e:
                # This specific error occurs during asyncio shutdown
                if "cancel scope in a different task" in str(e):
                    # This is expected during shutdown - suppress the error
                    pass
                else:
                    logger.debug(f"Runtime error during MCP disconnect: {e}")
            except asyncio.CancelledError:
                # Task was cancelled - this is expected during shutdown
                logger.debug("MCP disconnect cancelled during shutdown")
                # Don't re-raise during cleanup to allow graceful shutdown
            except Exception as e:
                logger.debug(f"Error during MCP disconnect (may be expected): {e}")
            finally:
                self._stdio_client = None
                self._read_stream = None
                self._write_stream = None
                self._creation_task = None
            
    async def _discover_capabilities(self) -> None:
        """Discover server capabilities (tools, resources, prompts)."""
        if not self.session:
            raise MCPConnectionError("Not connected to MCP server")
            
        try:
            # List tools
            tools_result = await self.session.list_tools()
            if tools_result.tools:
                for tool in tools_result.tools:
                    mcp_tool = MCPTool(
                        name=tool.name,
                        description=tool.description or "",
                        inputSchema=tool.inputSchema if isinstance(tool.inputSchema, dict) else {}
                    )
                    self.tools[tool.name] = mcp_tool
                    logger.debug(f"Discovered tool: {tool.name}")
            
            # List resources
            try:
                resources_result = await self.session.list_resources()
                if resources_result.resources:
                    for resource in resources_result.resources:
                        mcp_resource = MCPResource(
                            uri=resource.uri,
                            name=resource.name,
                            description=resource.description,
                            mimeType=resource.mimeType
                        )
                        self.resources[resource.uri] = mcp_resource
                        logger.debug(f"Discovered resource: {resource.uri}")
            except Exception:
                # Resources not supported
                pass
                
            # List prompts
            try:
                prompts_result = await self.session.list_prompts()
                if prompts_result.prompts:
                    for prompt in prompts_result.prompts:
                        mcp_prompt = MCPPrompt(
                            name=prompt.name,
                            description=prompt.description or "",
                            arguments=prompt.arguments if hasattr(prompt, 'arguments') else None
                        )
                        self.prompts[prompt.name] = mcp_prompt
                        logger.debug(f"Discovered prompt: {prompt.name}")
            except Exception:
                # Prompts not supported
                pass
                
        except Exception as e:
            logger.error(f"Failed to discover capabilities: {e}")
            raise MCPConnectionError(f"Failed to discover server capabilities: {e}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if not self.session:
            raise MCPConnectionError("Not connected to MCP server")
            
        if tool_name not in self.tools:
            raise MCPError(f"Tool '{tool_name}' not available on server '{self.name}'")
            
        try:
            result = await self.session.call_tool(tool_name, arguments)
            return result.content if hasattr(result, 'content') else result
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name}: {e}")
            raise MCPServerError(f"Failed to call tool: {e}")
    
    async def get_resource(self, uri: str) -> Any:
        """
        Get an MCP resource.
        
        Args:
            uri: Resource URI
            
        Returns:
            Resource content
        """
        if not self.session:
            raise MCPConnectionError("Not connected to MCP server")
            
        if uri not in self.resources:
            raise MCPError(f"Resource '{uri}' not available on server '{self.name}'")
            
        try:
            result = await self.session.read_resource(uri)
            return result.contents if hasattr(result, 'contents') else result
        except Exception as e:
            logger.error(f"Failed to get resource {uri}: {e}")
            raise MCPServerError(f"Failed to get resource: {e}")
    
    async def get_prompt(self, prompt_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """
        Get an MCP prompt.
        
        Args:
            prompt_name: Name of the prompt
            arguments: Prompt arguments
            
        Returns:
            Prompt content
        """
        if not self.session:
            raise MCPConnectionError("Not connected to MCP server")
            
        if prompt_name not in self.prompts:
            raise MCPError(f"Prompt '{prompt_name}' not available on server '{self.name}'")
            
        try:
            result = await self.session.get_prompt(prompt_name, arguments or {})
            return result.messages if hasattr(result, 'messages') else result
        except Exception as e:
            logger.error(f"Failed to get prompt {prompt_name}: {e}")
            raise MCPServerError(f"Failed to get prompt: {e}")
    
    def get_available_tools(self) -> List[str]:
        """
        Get list of available tool names.
        
        Returns:
            List of tool names
        """
        return list(self.tools.keys())
    
    def is_connected(self) -> bool:
        """
        Check if the client is connected to the MCP server.
        
        Returns:
            True if connected, False otherwise
        """
        return self.session is not None