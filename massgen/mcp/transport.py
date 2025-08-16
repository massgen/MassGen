"""
MCP transport layer implementations.
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .exceptions import MCPConnectionError, MCPTimeoutError, MCPProtocolError


@dataclass
class MCPMessage:
    """MCP JSON-RPC message structure."""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        msg = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            msg["id"] = self.id
        if self.method is not None:
            msg["method"] = self.method
        if self.params is not None:
            msg["params"] = self.params
        if self.result is not None:
            msg["result"] = self.result
        if self.error is not None:
            msg["error"] = self.error
        return msg

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPMessage":
        """Create message from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error")
        )


class MCPTransport(ABC):
    """Abstract base class for MCP transport implementations."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to MCP server."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to MCP server."""
        pass

    @abstractmethod
    async def send_message(self, message: MCPMessage) -> None:
        """Send message to MCP server."""
        pass

    @abstractmethod
    async def receive_message(self) -> Optional[MCPMessage]:
        """Receive message from MCP server."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        pass


class StdioTransport(MCPTransport):
    """MCP transport using stdio (subprocess communication)."""

    def __init__(self, command: List[str], cwd: Optional[str] = None):
        self.command = command
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None
        self._connected = False

    async def connect(self) -> None:
        """Start MCP server process and establish stdio connection."""
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd
            )
            self._connected = True
            
            # Send initialize request
            init_message = MCPMessage(
                id=str(uuid.uuid4()),
                method="initialize",
                params={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {"listChanged": True},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "massgen",
                        "version": "0.0.8"
                    }
                }
            )
            await self.send_message(init_message)
            
            # Wait for initialize response
            response = await self.receive_message()
            if response and response.error:
                raise MCPConnectionError(f"Initialize failed: {response.error}")
                
        except Exception as e:
            self._connected = False
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}")

    async def disconnect(self) -> None:
        """Terminate MCP server process."""
        if self.process:
            try:
                # Check if process is still running before trying to terminate
                if self.process.returncode is None:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Only try to kill if process is still running
                if self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
            except ProcessLookupError:
                # Process already terminated, just clean up
                pass
            finally:
                self.process = None
                self._connected = False

    async def send_message(self, message: MCPMessage) -> None:
        """Send JSON-RPC message via stdin."""
        if not self.process or not self.process.stdin:
            raise MCPConnectionError("Not connected to MCP server")
            
        try:
            json_data = json.dumps(message.to_dict()) + "\n"
            self.process.stdin.write(json_data.encode())
            await self.process.stdin.drain()
        except Exception as e:
            raise MCPConnectionError(f"Failed to send message: {e}")

    async def receive_message(self) -> Optional[MCPMessage]:
        """Receive JSON-RPC message from stdout."""
        if not self.process or not self.process.stdout:
            raise MCPConnectionError("Not connected to MCP server")
            
        try:
            line = await asyncio.wait_for(
                self.process.stdout.readline(), 
                timeout=30.0
            )
            
            if not line:
                return None
                
            data = json.loads(line.decode().strip())
            return MCPMessage.from_dict(data)
            
        except asyncio.TimeoutError:
            raise MCPTimeoutError("Timeout waiting for MCP server response")
        except json.JSONDecodeError as e:
            raise MCPProtocolError(f"Invalid JSON from MCP server: {e}")
        except Exception as e:
            raise MCPConnectionError(f"Failed to receive message: {e}")

    def is_connected(self) -> bool:
        """Check if connected to MCP server."""
        return self._connected and self.process is not None


class HTTPTransport(MCPTransport):
    """MCP transport using HTTP with Server-Sent Events."""
    
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {}
        self._connected = False
        # TODO: Implement HTTP transport using aiohttp
        
    async def connect(self) -> None:
        """Establish HTTP connection to MCP server."""
        # TODO: Implement HTTP connection
        raise NotImplementedError("HTTP transport not yet implemented")
        
    async def disconnect(self) -> None:
        """Close HTTP connection."""
        # TODO: Implement HTTP disconnection
        pass
        
    async def send_message(self, message: MCPMessage) -> None:
        """Send message via HTTP POST."""
        # TODO: Implement HTTP message sending
        raise NotImplementedError("HTTP transport not yet implemented")
        
    async def receive_message(self) -> Optional[MCPMessage]:
        """Receive message via Server-Sent Events."""
        # TODO: Implement SSE message receiving
        raise NotImplementedError("HTTP transport not yet implemented")
        
    def is_connected(self) -> bool:
        """Check HTTP connection status."""
        return self._connected