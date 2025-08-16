"""
MCP (Model Context Protocol) integration for MassGen.

This module provides MCP client functionality to connect with MCP servers
and integrate external tools and resources into the MassGen workflow.
"""

from .client import MCPClient
from .transport import StdioTransport, HTTPTransport
from .exceptions import MCPError, MCPConnectionError, MCPTimeoutError

__all__ = [
    "MCPClient",
    "StdioTransport", 
    "HTTPTransport",
    "MCPError",
    "MCPConnectionError", 
    "MCPTimeoutError"
]