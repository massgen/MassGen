"""
MCP client implementation for connecting to MCP servers.
"""

import asyncio
import uuid
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

from .transport import MCPTransport, StdioTransport, HTTPTransport, MCPMessage
from .exceptions import MCPError, MCPConnectionError, MCPServerError


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


class MCPClient:
    """MCP client for communicating with MCP servers."""

    def __init__(self, server_config: Dict[str, Any]):
        """
        Initialize MCP client.
        
        Args:
            server_config: Server configuration dict with keys:
                - name: Server name
                - type: Transport type ("stdio" or "http")
                - command: Command to run (for stdio)
                - url: Server URL (for http)
                - cwd: Working directory (for stdio)
        """
        self.config = server_config
        self.name = server_config["name"]
        self.transport = self._create_transport(server_config)
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.prompts: Dict[str, MCPPrompt] = {}
        self._request_id_counter = 0

    def _create_transport(self, config: Dict[str, Any]) -> MCPTransport:
        """Create appropriate transport based on config."""
        transport_type = config.get("type", "stdio")
        
        if transport_type == "stdio":
            command = config.get("command", [])
            args = config.get("args", [])
            cwd = config.get("cwd")
            
            # Handle different command formats
            if isinstance(command, str):
                # Single command string + args list
                full_command = [command] + args
            elif isinstance(command, list):
                # Command already a list
                full_command = command + args
            else:
                full_command = args
                
            return StdioTransport(full_command, cwd)
            
        elif transport_type == "http":
            url = config["url"]
            headers = config.get("headers", {})
            return HTTPTransport(url, headers)
            
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")

    def _next_request_id(self) -> str:
        """Generate next request ID."""
        self._request_id_counter += 1
        return f"req_{self._request_id_counter}_{uuid.uuid4().hex[:8]}"

    async def connect(self) -> None:
        """Connect to MCP server and discover capabilities."""
        await self.transport.connect()
        
        # Discover available tools, resources, and prompts
        await self._discover_capabilities()

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        await self.transport.disconnect()

    async def _discover_capabilities(self) -> None:
        """Discover server capabilities (tools, resources, prompts)."""
        try:
            # List tools
            tools_response = await self._send_request("tools/list")
            if tools_response.get("tools"):
                for tool_data in tools_response["tools"]:
                    tool = MCPTool(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        inputSchema=tool_data.get("inputSchema", {})
                    )
                    self.tools[tool.name] = tool

            # List resources
            try:
                resources_response = await self._send_request("resources/list")
                if resources_response.get("resources"):
                    for resource_data in resources_response["resources"]:
                        resource = MCPResource(
                            uri=resource_data["uri"],
                            name=resource_data["name"],
                            description=resource_data.get("description"),
                            mimeType=resource_data.get("mimeType")
                        )
                        self.resources[resource.uri] = resource
            except MCPServerError:
                # Resources not supported by this server
                pass

            # List prompts
            try:
                prompts_response = await self._send_request("prompts/list")
                if prompts_response.get("prompts"):
                    for prompt_data in prompts_response["prompts"]:
                        prompt = MCPPrompt(
                            name=prompt_data["name"],
                            description=prompt_data.get("description", ""),
                            arguments=prompt_data.get("arguments")
                        )
                        self.prompts[prompt.name] = prompt
            except MCPServerError:
                # Prompts not supported by this server
                pass
                
        except Exception as e:
            raise MCPConnectionError(f"Failed to discover server capabilities: {e}")

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Send JSON-RPC request and wait for response."""
        request_id = self._next_request_id()
        request = MCPMessage(
            id=request_id,
            method=method,
            params=params
        )
        
        await self.transport.send_message(request)
        
        # Wait for response
        while True:
            response = await self.transport.receive_message()
            if response and response.id == request_id:
                if response.error:
                    raise MCPServerError(
                        response.error.get("message", "Unknown error"),
                        response.error.get("code")
                    )
                return response.result
            # Ignore other messages or handle notifications

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if tool_name not in self.tools:
            raise MCPError(f"Tool '{tool_name}' not available on server '{self.name}'")
            
        return await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

    async def get_resource(self, uri: str) -> Any:
        """
        Get resource content by URI.
        
        Args:
            uri: Resource URI
            
        Returns:
            Resource content
        """
        return await self._send_request("resources/read", {
            "uri": uri
        })

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """
        Get prompt template.
        
        Args:
            name: Prompt name
            arguments: Prompt arguments
            
        Returns:
            Prompt content
        """
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
            
        return await self._send_request("prompts/get", params)

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
        return self.transport.is_connected()