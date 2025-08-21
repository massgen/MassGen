"""
MCP (Model Context Protocol) integration for MassGen.

This module provides MCP client functionality to connect with MCP servers
and integrate external tools and resources into the MassGen workflow.
"""

from .client import MCPClient
from .transport import StdioTransport, HTTPTransport
from .exceptions import MCPError, MCPConnectionError, MCPTimeoutError

# Try to import SDK-based client
try:
    from .client_sdk import MCPClientSDK
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCPClientSDK = None
    MCP_SDK_AVAILABLE = False

__all__ = [
    "MCPClient",
    "MCPClientSDK",
    "StdioTransport",
    "HTTPTransport",
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "MCP_SDK_AVAILABLE",
]
